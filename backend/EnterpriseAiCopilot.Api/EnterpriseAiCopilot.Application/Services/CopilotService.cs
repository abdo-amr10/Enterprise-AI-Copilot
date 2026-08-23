using System;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.Common.Models;
using EnterpriseAiCopilot.Application.DTOs.Copilot;
using EnterpriseAiCopilot.Domain.Entities;

namespace EnterpriseAiCopilot.Application.Services
{
    public class CopilotService : ICopilotService
    {
        private readonly IApplicationDbContext _context;
        private readonly IAiRuntimeClient _aiRuntimeClient;
        private readonly IDynamicSqlExecutor _sqlExecutor;
        private readonly ILogger<CopilotService> _logger;

        public CopilotService(
            IApplicationDbContext context,
            IAiRuntimeClient aiRuntimeClient,
            IDynamicSqlExecutor sqlExecutor,
            ILogger<CopilotService> logger)
        {
            _context = context;
            _aiRuntimeClient = aiRuntimeClient;
            _sqlExecutor = sqlExecutor;
            _logger = logger;
        }

        public async Task<Result<AskCopilotResponse>> AskQuestionAsync(
            AskCopilotRequest request,
            string userId,
            int branchId,
            CancellationToken cancellationToken = default)
        {
            var stopwatch = Stopwatch.StartNew();
            Guid layerId;

            try
            {
                var activeLayer = await _context.SemanticLayers
                    .FirstOrDefaultAsync(
                        sl => sl.IsActive,
                        cancellationToken);

                if (activeLayer == null)
                {
                    return Result<AskCopilotResponse>.Failure(
                        "SEMANTIC_LAYER_NOT_APPROVED: No active semantic layer found to process the request.");
                }

                layerId = activeLayer.Id;
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                _logger.LogError(
                    ex,
                    "Failed to retrieve active semantic layer.");

                return Result<AskCopilotResponse>.Failure(
                    "DATABASE_ERROR: Could not retrieve semantic layer.");
            }

            AiRuntimeResponse aiResponse;

            try
            {
                aiResponse =
                    await _aiRuntimeClient.ProcessQuestionAsync(
                        request,
                        cancellationToken);
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                stopwatch.Stop();

                _logger.LogError(
                    ex,
                    "AI Runtime client failed.");

                await LogQueryHistorySafeAsync(
                    userId,
                    branchId,
                    request.Question,
                    null,
                    layerId,
                    "Failed",
                    "AI_RUNTIME_ERROR: Failed to process question with AI.",
                    stopwatch.ElapsedMilliseconds,
                    cancellationToken);

                return Result<AskCopilotResponse>.Failure(
                    "AI_RUNTIME_ERROR: Failed to process question with AI.");
            }

            if (!aiResponse.IsSuccess ||
                string.IsNullOrWhiteSpace(aiResponse.GeneratedSql))
            {
                stopwatch.Stop();

                var errorMessage =
                    aiResponse.ErrorMessage ??
                    "SQL_GENERATION_FAILED";

                await LogQueryHistorySafeAsync(
                    userId,
                    branchId,
                    request.Question,
                    null,
                    layerId,
                    "Failed",
                    errorMessage,
                    stopwatch.ElapsedMilliseconds,
                    cancellationToken);

                return Result<AskCopilotResponse>.Failure(errorMessage);
            }

            var executionResult =
                await _sqlExecutor.ExecuteQueryAsync(
                    aiResponse.GeneratedSql,
                    branchId,
                    cancellationToken);

            stopwatch.Stop();

            var executionError =
                executionResult.IsSuccess
                    ? null
                    : executionResult.ErrorMessage;

            var queryResult =
                executionResult.IsSuccess
                    ? executionResult.Data
                    : null;

            var status =
                executionError == null
                    ? "Completed"
                    : "Failed";

            var historyId =
                await LogQueryHistorySafeAsync(
                    userId,
                    branchId,
                    request.Question,
                    aiResponse.GeneratedSql,
                    layerId,
                    status,
                    executionError,
                    stopwatch.ElapsedMilliseconds,
                    cancellationToken);

            if (historyId == Guid.Empty)
            {
                return Result<AskCopilotResponse>.Failure(
                    "DATABASE_ERROR: Failed to persist query history audit.");
            }

            if (executionError != null)
            {
                return Result<AskCopilotResponse>.Failure(
                    executionError);
            }

            var response = new AskCopilotResponse
            {
                QueryId = historyId.ToString(),
                Status = "Completed",
                Report = new CopilotReport
                {
                    TextSummary =
                        aiResponse.TextSummary ??
                        "Query executed successfully.",
                    PresentationType =
                        aiResponse.PresentationType,
                    Data = queryResult
                }
            };

            return Result<AskCopilotResponse>.Success(response);
        }

        public async Task<Result<QueryHistoryResponse>> GetUserHistoryAsync(
            string userId,
            int branchId,
            CancellationToken cancellationToken = default)
        {
            try
            {
                var historyItems =
                    await _context.CopilotQueryHistories
                        .Where(h =>
                            h.UserId == userId &&
                            h.BranchId == branchId)
                        .OrderByDescending(h => h.CreatedAt)
                        .Select(h => new QueryHistoryItemResponse
                        {
                            QueryId = h.Id.ToString(),
                            Question = h.UserPrompt,
                            Status = h.Status,
                            CreatedAt =
                                h.CreatedAt.ToString(
                                    "yyyy-MM-ddTHH:mm:ssZ")
                        })
                        .ToListAsync(cancellationToken);

                return Result<QueryHistoryResponse>.Success(
                    new QueryHistoryResponse
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
                _logger.LogError(
                    ex,
                    "Error retrieving query history for user {UserId} and branch {BranchId}",
                    userId,
                    branchId);

                return Result<QueryHistoryResponse>.Failure(
                    "DATABASE_ERROR: Failed to retrieve history.");
            }
        }

        public async Task<Result<QueryDetailsResponse>> GetQueryDetailsAsync(
            string queryId,
            string userId,
            int branchId,
            CancellationToken cancellationToken = default)
        {
            if (!Guid.TryParse(queryId, out var id))
            {
                return Result<QueryDetailsResponse>.Failure(
                    "Invalid Query ID format.");
            }

            try
            {
                var history =
                    await _context.CopilotQueryHistories
                        .FirstOrDefaultAsync(
                            h =>
                                h.Id == id &&
                                h.UserId == userId &&
                                h.BranchId == branchId,
                            cancellationToken);

                if (history == null)
                {
                    return Result<QueryDetailsResponse>.Failure(
                        "Query not found or you do not have permission to view it.");
                }

                var response = new QueryDetailsResponse
                {
                    QueryId = history.Id.ToString(),
                    Question = history.UserPrompt,
                    Status = history.Status,
                    CreatedAt =
                        history.CreatedAt.ToString(
                            "yyyy-MM-ddTHH:mm:ssZ"),
                    GeneratedSql = history.GeneratedSql,
                    ExecutionTimeMs = history.ExecutionTimeMs,
                    ErrorMessage = history.ErrorMessage,
                    SemanticLayerId =
                        history.SemanticLayerId.ToString(),
                    Result = new CopilotReportSummary
                    {
                        TextSummary =
                            history.Status == "Completed"
                                ? "Query executed successfully."
                                : $"Query failed: {history.ErrorMessage}",
                        PresentationType =
                            history.Status == "Completed"
                                ? "DataTable"
                                : "ErrorCard"
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
                _logger.LogError(
                    ex,
                    "Error retrieving query details for ID {QueryId}",
                    queryId);

                return Result<QueryDetailsResponse>.Failure(
                    "DATABASE_ERROR: Failed to retrieve query details.");
            }
        }

        private async Task<Guid> LogQueryHistorySafeAsync(
            string userId,
            int branchId,
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

                await _context.SaveChangesAsync(
                    cancellationToken);

                return history.Id;
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                _logger.LogError(
                    ex,
                    "Critical error: Failed to save query history to database.");

                return Guid.Empty;
            }
        }
    }
}