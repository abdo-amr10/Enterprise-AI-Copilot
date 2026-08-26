using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.Common.Models;
using EnterpriseAiCopilot.Application.DTOs.Copilot;
using EnterpriseAiCopilot.Domain.Constants;
using EnterpriseAiCopilot.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using System;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace EnterpriseAiCopilot.Application.Services
{
    public class CopilotService : ICopilotService
    {
        private readonly IApplicationDbContext _context;
        private readonly IAiRuntimeClient _aiRuntimeClient;
        private readonly IDynamicSqlExecutor _sqlExecutor;
        private readonly ILogger<CopilotService> _logger;
        private readonly IAuditService _auditService;
        private readonly IAiResultFormatterClient _resultFormatter;
        public CopilotService(
            IApplicationDbContext context,
            IAiRuntimeClient aiRuntimeClient,
            IDynamicSqlExecutor sqlExecutor,
            ILogger<CopilotService> logger,
            IAuditService auditService,
            IAiResultFormatterClient resultFormatter)
        {
            _context = context;
            _aiRuntimeClient = aiRuntimeClient;
            _sqlExecutor = sqlExecutor;
            _logger = logger;
            _auditService = auditService;
            _resultFormatter = resultFormatter;
        }

        public async Task<Result<AskCopilotResponse>> AskQuestionAsync(
            AskCopilotRequest request,
            string userId,
            string branchId,
            CancellationToken cancellationToken = default)
        {
            Guid layerId;

            try
            {
                var activeLayer = await _context.SemanticLayers
                    .Where(sl => sl.IsActive)
                    .OrderByDescending(sl => sl.CreatedAt)
                    .FirstOrDefaultAsync(cancellationToken);

                if (activeLayer == null)
                {
                    return Result<AskCopilotResponse>.Failure("SEMANTIC_LAYER_NOT_APPROVED: No active semantic layer found to process the request.");
                }

                layerId = activeLayer.Id;
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to retrieve active semantic layer.");
                return Result<AskCopilotResponse>.Failure("DATABASE_ERROR: Could not retrieve semantic layer.");
            }

            int maxRetries = 3;
            int attempt = 0;
            string originalPrompt = request.Question;
            long totalExecutionTimeMs = 0;
            var stopwatch = new Stopwatch();

            AiRuntimeResponse? aiResponse = null;
            Result<object>? executionResult = null;
            string? finalErrorMessage = null;

            while (attempt < maxRetries)
            {
                stopwatch.Restart();
                var currentRequest = new AskCopilotRequest
                {
                    Question = originalPrompt,
                    Conversation = request.Conversation ?? new List<ConversationMessage>()
                };

                try
                {
                    aiResponse = await _aiRuntimeClient.ProcessQuestionAsync(currentRequest, cancellationToken);
                }
                catch (OperationCanceledException)
                {
                    throw;
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "AI Runtime client failed.");
                    finalErrorMessage = "AI_RUNTIME_ERROR: Failed to process question with AI.";
                    break;
                }

                if (!aiResponse.IsSuccess || string.IsNullOrWhiteSpace(aiResponse.GeneratedSql))
                {
                    finalErrorMessage = aiResponse.ErrorMessage ?? "SQL_GENERATION_FAILED";
                    break;
                }

                _logger.LogInformation(
                    "Copilot SQL generated on attempt {Attempt}: {GeneratedSql}",
                    attempt + 1,
                    aiResponse.GeneratedSql);

                executionResult = await _sqlExecutor.ExecuteQueryAsync(aiResponse.GeneratedSql, branchId, cancellationToken);
                
                stopwatch.Stop();
                totalExecutionTimeMs += stopwatch.ElapsedMilliseconds;

                if (executionResult.IsSuccess)
                {
                    finalErrorMessage = null;
                    break;
                }

                finalErrorMessage = executionResult.ErrorMessage;

                if (finalErrorMessage != null &&
                       (finalErrorMessage.StartsWith("SQL_VALIDATION_FAILED") ||
                        finalErrorMessage.StartsWith("RLS_ERROR") ||
                        finalErrorMessage.StartsWith("DATABASE_EXECUTION_ERROR")))
                {
                    _logger.LogWarning($"Attempt {attempt + 1} failed. Triggering Self-Correction. Error: {finalErrorMessage}");
                    
                    currentRequest.Conversation.Add(new ConversationMessage
                    {
                        Role = "system",
                        Content = $"RLS_CORRECTION: The previous SQL was '{aiResponse.GeneratedSql}'. " +
                                  $"It failed with '{finalErrorMessage}'. Generate a replacement SQL query " +
                                  "that fixes this exact policy failure while preserving the original question."
                    });
                    request.Conversation = currentRequest.Conversation;
                    
                    attempt++;
                }
                else
                {
                    break;
                }
            }

            var status = (executionResult != null && executionResult.IsSuccess) ? "Completed" : "Failed";

            var historyId = await LogQueryHistorySafeAsync(
                 userId,
                 branchId,
                 originalPrompt,
                 aiResponse?.GeneratedSql,
                 layerId,
                 status,
                 finalErrorMessage,
                 totalExecutionTimeMs,
                 cancellationToken);

            if (historyId == Guid.Empty)
            {
                return Result<AskCopilotResponse>.Failure("DATABASE_ERROR: Failed to persist query history audit.");
            }

            if (finalErrorMessage != null)
            {
                await _auditService.LogEventAsync(
                    action: AuditActions.QueryFailed,
                    userId: userId,
                    status: "Failed",
                    resourceId: historyId.ToString(),
                    cancellationToken: cancellationToken
                );

                return Result<AskCopilotResponse>.Failure(finalErrorMessage);
            }

            await _auditService.LogEventAsync(
                action: AuditActions.QueryExecution,
                userId: userId,
                status: "Success",
                resourceId: historyId.ToString(),
                cancellationToken: cancellationToken
            );

            var formattedReport = await _resultFormatter.FormatExecutionResultAsync(
                originalPrompt,
                executionResult!.Data!,
                cancellationToken);

            var response = new AskCopilotResponse
            {
                QueryId = historyId.ToString(),
                Status = "Completed",
                Report = new CopilotReport
                {
                    TextSummary = formattedReport.TextSummary,
                    PresentationType = formattedReport.PresentationType,
                    Data = executionResult.Data
                }
            };

            return Result<AskCopilotResponse>.Success(response);
        } 

        public async Task<Result<QueryHistoryResponse>> GetUserHistoryAsync(
            string userId,
            string branchId,
            CancellationToken cancellationToken = default)
        {
            try
            {
                var historyItems = await _context.CopilotQueryHistories
                    .Where(h => h.UserId == userId && h.BranchId == branchId)
                    .OrderByDescending(h => h.CreatedAt)
                    .Select(h => new QueryHistoryItemResponse
                    {
                        QueryId = h.Id.ToString(),
                        Question = h.UserPrompt,
                        Status = h.Status,
                        CreatedAt = h.CreatedAt.ToString("yyyy-MM-ddTHH:mm:ssZ")
                    })
                    .ToListAsync(cancellationToken);

                return Result<QueryHistoryResponse>.Success(new QueryHistoryResponse
                {
                    Items = historyItems
                });
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error retrieving query history for user {UserId} and branch {BranchId}", userId, branchId);
                return Result<QueryHistoryResponse>.Failure("DATABASE_ERROR: Failed to retrieve history.");
            }
        }

        public async Task<Result<QueryDetailsResponse>> GetQueryDetailsAsync(
            string queryId,
            string userId,
            string branchId,
            CancellationToken cancellationToken = default)
        {
            if (!Guid.TryParse(queryId, out var id))
            {
                return Result<QueryDetailsResponse>.Failure("Invalid Query ID format.");
            }

            try
            {
                var history = await _context.CopilotQueryHistories
                    .FirstOrDefaultAsync(h => h.Id == id && h.UserId == userId && h.BranchId == branchId, cancellationToken);

                if (history == null)
                {
                    return Result<QueryDetailsResponse>.Failure("Query not found or you do not have permission to view it.");
                }

                var response = new QueryDetailsResponse
                {
                    QueryId = history.Id.ToString(),
                    Question = history.UserPrompt,
                    Status = history.Status,
                    CreatedAt = history.CreatedAt.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                    GeneratedSql = history.GeneratedSql,
                    ExecutionTimeMs = history.ExecutionTimeMs,
                    ErrorMessage = history.ErrorMessage,
                    SemanticLayerId = history.SemanticLayerId.ToString(),
                    Result = new CopilotReportSummary
                    {
                        TextSummary = history.Status == "Completed" ? "Query executed successfully." : $"Query failed: {history.ErrorMessage}",
                        PresentationType = history.Status == "Completed" ? "DataTable" : "ErrorCard"
                    }
                };

                return Result<QueryDetailsResponse>.Success(response);
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error retrieving query details for ID {QueryId}", queryId);
                return Result<QueryDetailsResponse>.Failure("DATABASE_ERROR: Failed to retrieve query details.");
            }
        }

        private async Task<Guid> LogQueryHistorySafeAsync(
            string userId,
            string branchId,
            string prompt,
            string? sql,
            Guid layerId,
            string status,
            string? error,
            long executionTime,
            CancellationToken cancellationToken)
        {
            try
            {
                var history = new CopilotQueryHistory
                {
                    UserId = userId,
                    BranchId = branchId,
                    UserPrompt = prompt,
                    GeneratedSql = sql,
                    SemanticLayerId = layerId,
                    Status = status,
                    ErrorMessage = error,
                    ExecutionTimeMs = executionTime
                };

                _context.CopilotQueryHistories.Add(history);
                await _context.SaveChangesAsync(cancellationToken);

                return history.Id;
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Critical error: Failed to save query history to database.");
                return Guid.Empty;
            }
        }
    }
}
