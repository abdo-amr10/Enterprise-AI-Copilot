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
using System.Text.Json;
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

            Conversation? conversation = null;
            if (!string.IsNullOrWhiteSpace(request.ConversationId))
            {
                if (!Guid.TryParse(request.ConversationId, out var requestedConversationId))
                    return Result<AskCopilotResponse>.Failure("CONVERSATION_ERROR: Invalid conversation ID.");

                conversation = await _context.Conversations.FirstOrDefaultAsync(
                    c => c.Id == requestedConversationId && c.UserId == userId && c.BranchId == branchId && !c.IsArchived,
                    cancellationToken);

                if (conversation == null)
                    return Result<AskCopilotResponse>.Failure("CONVERSATION_NOT_FOUND: Conversation was not found or is not available.");

                if (conversation.SemanticLayerId != layerId)
                    return Result<AskCopilotResponse>.Failure("CONVERSATION_SEMANTIC_LAYER_CHANGED: This conversation belongs to an older semantic layer. Start a new conversation.");
            }
            else
            {
                conversation = new Conversation
                {
                    UserId = userId,
                    BranchId = branchId,
                    SemanticLayerId = layerId,
                    Title = request.Question.Length > 200 ? request.Question[..200] : request.Question
                };
                _context.Conversations.Add(conversation);
                await _context.SaveChangesAsync(cancellationToken);
            }

            var conversationId = conversation.Id;
            var conversationMessages = await LoadConversationMessagesAsync(conversationId, userId, branchId, cancellationToken);
            if (conversationMessages.Count == 0 && request.Conversation is { Count: > 0 })
                conversationMessages = request.Conversation;

            int maxRetries = 3;
            int attempt = 0;
            string originalPrompt = request.Question;
            long totalExecutionTimeMs = 0;
            var stopwatch = new Stopwatch();

            AiRuntimeResponse? aiResponse = null;
            Result<object>? executionResult = null;
            CopilotReport? directReport = null;
            bool aiHandledWithoutSql = false;
            string? finalErrorMessage = null;

            while (attempt < maxRetries)
            {
                stopwatch.Restart();
                var currentRequest = new AskCopilotRequest
                {
                    Question = originalPrompt,
                    ConversationId = conversationId.ToString(),
                    TenantId = branchId,
                    // These values are authoritative server-side context. Do not trust
                    // equivalent values supplied by the client request body.
                    UserId = userId,
                    BranchId = branchId,
                    SemanticRevisionId = layerId.ToString(),
                    SchemaVersion = "1.0",
                    LastResultMetadata = await LoadLastResultMetadataAsync(
                        conversationId,
                        userId,
                        branchId,
                        cancellationToken),
                    Conversation = new List<ConversationMessage>(conversationMessages)
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

                var route = aiResponse.Route?.Trim();
                var isDirectResponseRoute =
                    string.IsNullOrWhiteSpace(aiResponse.GeneratedSql) &&
                    (
                        !string.IsNullOrWhiteSpace(aiResponse.DirectAnswer) ||
                        string.Equals(route, "DirectAnswer", StringComparison.OrdinalIgnoreCase) ||
                        string.Equals(route, "SafeRejection", StringComparison.OrdinalIgnoreCase) ||
                        string.Equals(route, "RESULT_ANSWER", StringComparison.OrdinalIgnoreCase) ||
                        string.Equals(route, "UNRESOLVED_CONTEXT", StringComparison.OrdinalIgnoreCase) ||
                        string.Equals(route, "EXACT_REPLAY", StringComparison.OrdinalIgnoreCase) ||
                        string.Equals(route, "CAPABILITY", StringComparison.OrdinalIgnoreCase)
                    );

                if (isDirectResponseRoute)
                {
                    stopwatch.Stop();
                    totalExecutionTimeMs += stopwatch.ElapsedMilliseconds;
                    directReport = new CopilotReport
                    {
                        TextSummary = aiResponse.DirectAnswer ?? aiResponse.TextSummary ?? "The request was answered directly.",
                        PresentationType = string.Equals(route, "SafeRejection", StringComparison.OrdinalIgnoreCase)
                            ? "SafeRejection"
                            : "DirectAnswer",
                        Data = null,
                        ExecutionTimeMs = totalExecutionTimeMs
                    };
                    aiHandledWithoutSql = true;
                    finalErrorMessage = null;
                    break;
                }

                if (!aiResponse.IsSuccess)
                {
                    finalErrorMessage = aiResponse.ErrorMessage ?? "AI_PROCESSING_FAILED";
                    break;
                }

                if (string.IsNullOrWhiteSpace(aiResponse.GeneratedSql))
                {
                    finalErrorMessage = aiResponse.ErrorMessage ?? "SQL_GENERATION_FAILED: No query was generated.";
                    break;
                }

                _logger.LogInformation(
                    "Copilot SQL generated on attempt {Attempt}: {GeneratedSql}",
                    attempt + 1,
                    aiResponse.GeneratedSql);

                if (!Guid.TryParse(userId, out var parsedUserId))
                {
                    return Result<AskCopilotResponse>.Failure("AUTHENTICATION_ERROR: Invalid user ID.");
                }

                executionResult = await _sqlExecutor.ExecuteQueryAsync(
                    aiResponse.GeneratedSql,
                    branchId,
                    layerId,
                    parsedUserId,
                    cancellationToken);

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

                    conversationMessages.Add(new ConversationMessage
                    {
                        Role = "system",
                        Content = $"RLS_CORRECTION: The previous SQL was '{aiResponse.GeneratedSql}'. " +
                                  $"It failed with '{finalErrorMessage}'. Generate a replacement SQL query " +
                                  "that fixes this exact policy failure while preserving the original question."
                    });
                    attempt++;
                }
                else
                {
                    break;
                }
            }

            var status = (aiHandledWithoutSql || (executionResult != null && executionResult.IsSuccess))
                ? "Completed"
                : "Failed";

            var historyId = await LogQueryHistorySafeAsync(
                 userId,
                 branchId,
                 originalPrompt,
                 aiResponse?.ResolvedQuestion,
                 aiResponse?.GeneratedSql,
                 layerId,
                 conversationId,
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

                return Result<AskCopilotResponse>.Failure(finalErrorMessage, new AskCopilotResponse
                {
                    QueryId = historyId.ToString(),
                    ConversationId = conversationId.ToString(),
                    Status = "Failed",
                    ErrorCode = "BUSINESS_ERROR",
                    Message = finalErrorMessage
                });
            }

            await _auditService.LogEventAsync(
                action: AuditActions.QueryExecution,
                userId: userId,
                status: "Success",
                resourceId: historyId.ToString(),
                cancellationToken: cancellationToken
            );

            if (aiHandledWithoutSql)
            {
                await SaveQueryResultSafeAsync(historyId, directReport!, cancellationToken);
                conversation.UpdatedAt = DateTime.UtcNow;
                await _context.SaveChangesAsync(cancellationToken);

                return Result<AskCopilotResponse>.Success(new AskCopilotResponse
                {
                    QueryId = historyId.ToString(),
                    ConversationId = conversationId.ToString(),
                    Status = "Completed",
                    Report = directReport!
                });
            }

            CopilotReport formattedReport;
            try
            {
                formattedReport = await _resultFormatter.FormatExecutionResultAsync(
                    originalPrompt,
                    executionResult!.Data!,
                    cancellationToken);
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "AI Formatter failed to process the execution result. Using fallback report.");

                formattedReport = new CopilotReport
                {
                    TextSummary = "Query executed successfully, but we couldn't generate an AI summary at the moment.",
                    PresentationType = "DataTable",
                    Data = executionResult!.Data,
                    ExecutionTimeMs = totalExecutionTimeMs
                };
            }

            formattedReport.ExecutionTimeMs = totalExecutionTimeMs;

            await SaveQueryResultSafeAsync(historyId, formattedReport, cancellationToken);
            conversation.UpdatedAt = DateTime.UtcNow;
            await _context.SaveChangesAsync(cancellationToken);

            var response = new AskCopilotResponse
            {
                QueryId = historyId.ToString(),
                ConversationId = conversationId.ToString(),
                Status = "Completed",
                Report = formattedReport
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
                        ConversationId = h.ConversationId.HasValue ? h.ConversationId.Value.ToString() : null,
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

                CopilotReport? storedReport = null;
                if (history.Status == "Completed" && !string.IsNullOrWhiteSpace(history.ResultJson))
                {
                    try
                    {
                        storedReport = JsonSerializer.Deserialize<CopilotReport>(history.ResultJson);
                    }
                    catch (JsonException ex)
                    {
                        _logger.LogWarning(ex, "Stored report could not be deserialized for query {QueryId}", queryId);
                    }
                }

                var response = new QueryDetailsResponse
                {
                    QueryId = history.Id.ToString(),
                    ConversationId = history.ConversationId.HasValue ? history.ConversationId.Value.ToString() : null,
                    Question = history.UserPrompt,
                    Status = history.Status,
                    CreatedAt = history.CreatedAt.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                    GeneratedSql = history.GeneratedSql,
                    ExecutionTimeMs = history.ExecutionTimeMs,
                    ErrorMessage = history.ErrorMessage,
                    SemanticLayerId = history.SemanticLayerId.ToString(),
                    Result = storedReport ?? new CopilotReport
                    {
                        TextSummary = history.Status == "Completed" ? "Query executed successfully." : $"Query failed: {history.ErrorMessage}",
                        PresentationType = history.Status == "Completed" ? "DataTable" : "ErrorCard",
                        Data = DeserializeResultData(history.ResultJson),
                        ExecutionTimeMs = history.ExecutionTimeMs
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

        public async Task<Result<List<ConversationSummaryResponse>>> GetConversationsAsync(
            string userId, string branchId, CancellationToken cancellationToken = default)
        {
            var conversations = await _context.Conversations
                .Where(c => c.UserId == userId && c.BranchId == branchId && !c.IsArchived)
                .OrderByDescending(c => c.UpdatedAt ?? c.CreatedAt)
                .Select(c => new ConversationSummaryResponse
                {
                    ConversationId = c.Id.ToString(),
                    Title = c.Title,
                    LastQuestion = c.QueryHistories.OrderByDescending(q => q.CreatedAt).Select(q => q.UserPrompt).FirstOrDefault(),
                    CreatedAt = c.CreatedAt.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                    UpdatedAt = (c.UpdatedAt ?? c.CreatedAt).ToString("yyyy-MM-ddTHH:mm:ssZ")
                })
                .ToListAsync(cancellationToken);

            return Result<List<ConversationSummaryResponse>>.Success(conversations);
        }

        public async Task<Result<ConversationDetailsResponse>> GetConversationAsync(
            string conversationId, string userId, string branchId, CancellationToken cancellationToken = default)
        {
            if (!Guid.TryParse(conversationId, out var id))
                return Result<ConversationDetailsResponse>.Failure("Invalid Conversation ID format.");

            var conversation = await _context.Conversations.FirstOrDefaultAsync(
                c => c.Id == id && c.UserId == userId && c.BranchId == branchId && !c.IsArchived,
                cancellationToken);
            if (conversation == null)
                return Result<ConversationDetailsResponse>.Failure("Conversation not found or you do not have permission to view it.");

            var queries = await _context.CopilotQueryHistories
                .Where(q => q.ConversationId == id && q.UserId == userId && q.BranchId == branchId)
                .OrderBy(q => q.CreatedAt)
                .ToListAsync(cancellationToken);

            return Result<ConversationDetailsResponse>.Success(new ConversationDetailsResponse
            {
                ConversationId = conversation.Id.ToString(),
                Title = conversation.Title,
                CreatedAt = conversation.CreatedAt.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                UpdatedAt = (conversation.UpdatedAt ?? conversation.CreatedAt).ToString("yyyy-MM-ddTHH:mm:ssZ"),
                Turns = queries.Select(q => new ConversationTurnResponse
                {
                    QueryId = q.Id.ToString(),
                    Question = q.UserPrompt,
                    GeneratedSql = q.GeneratedSql,
                    ResolvedQuestion = q.ResolvedQuestion,
                    Status = q.Status,
                    ExecutionTimeMs = q.ExecutionTimeMs,
                    CreatedAt = q.CreatedAt.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                    ErrorMessage = q.ErrorMessage,
                    Result = q.ResultJson == null ? null : DeserializeReport(q.ResultJson)
                }).ToList()
            });
        }

        public async Task<Result<bool>> ArchiveConversationAsync(
            string conversationId, string userId, string branchId, CancellationToken cancellationToken = default)
        {
            if (!Guid.TryParse(conversationId, out var id))
                return Result<bool>.Failure("Invalid Conversation ID format.");

            var conversation = await _context.Conversations.FirstOrDefaultAsync(
                c => c.Id == id && c.UserId == userId && c.BranchId == branchId && !c.IsArchived,
                cancellationToken);
            if (conversation == null)
                return Result<bool>.Failure("Conversation not found or you do not have permission to modify it.");

            conversation.IsArchived = true;
            await _context.SaveChangesAsync(cancellationToken);
            return Result<bool>.Success(true);
        }

        private async Task<List<ConversationMessage>> LoadConversationMessagesAsync(
            Guid conversationId, string userId, string branchId, CancellationToken cancellationToken)
        {
            var queries = await _context.CopilotQueryHistories
                // Send the complete conversation to the AI, including failed
                // turns, so it can understand what was attempted and respond
                // consistently when the user repeats or clarifies the request.
                // The AI state adapter uses ExecutionStatus to ensure failed
                // SQL never becomes the last successful execution.
                .Where(q => q.ConversationId == conversationId &&
                            q.UserId == userId &&
                            q.BranchId == branchId)
                .OrderBy(q => q.CreatedAt)
                .ToListAsync(cancellationToken);

            var messages = new List<ConversationMessage>();
            foreach (var query in queries)
            {
                string? executionResultSummary = null;
                if (!string.IsNullOrWhiteSpace(query.ResultJson))
                {
                    var report = DeserializeReport(query.ResultJson);
                    executionResultSummary = report?.TextSummary;
                }

                messages.Add(new ConversationMessage
                {
                    Role = "turn",
                    TurnId = $"turn_{query.Id}",
                    UserQuestion = query.UserPrompt,
                    ResolvedQuestion = query.ResolvedQuestion,
                    GeneratedSql = query.GeneratedSql,
                    ExecutionResultSummary = executionResultSummary,
                    ExecutionStatus = query.Status,
                    Timestamp = query.CreatedAt.ToUniversalTime().ToString("O")
                });
            }
            return messages;
        }

        private async Task<object?> LoadLastResultMetadataAsync(
            Guid conversationId,
            string userId,
            string branchId,
            CancellationToken cancellationToken)
        {
            var latestCompletedQuery = await _context.CopilotQueryHistories
                .AsNoTracking()
                .Where(q => q.ConversationId == conversationId &&
                            q.UserId == userId &&
                            q.BranchId == branchId &&
                            q.Status == "Completed" &&
                            q.ResultJson != null)
                .OrderByDescending(q => q.CreatedAt)
                .FirstOrDefaultAsync(cancellationToken);

            if (latestCompletedQuery == null || string.IsNullOrWhiteSpace(latestCompletedQuery.ResultJson))
                return null;

            try
            {
                using var resultDocument = JsonDocument.Parse(latestCompletedQuery.ResultJson);
                return new
                {
                    queryId = latestCompletedQuery.Id.ToString(),
                    question = latestCompletedQuery.UserPrompt,
                    generatedSql = latestCompletedQuery.GeneratedSql,
                    result = resultDocument.RootElement.Clone()
                };
            }
            catch (JsonException ex)
            {
                _logger.LogWarning(ex, "Could not build last result metadata for conversation {ConversationId}", conversationId);
                return null;
            }
        }

        private static CopilotReport? DeserializeReport(string json)
        {
            try { return JsonSerializer.Deserialize<CopilotReport>(json); }
            catch (JsonException) { return null; }
        }

        private async Task<Guid> LogQueryHistorySafeAsync(
            string userId,
            string branchId,
            string prompt,
            string? resolvedQuestion,
            string? sql,
            Guid layerId,
            Guid conversationId,
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
                    ResolvedQuestion = resolvedQuestion,
                    GeneratedSql = sql,
                    SemanticLayerId = layerId,
                    ConversationId = conversationId,
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

        private async Task SaveQueryResultSafeAsync(
            Guid historyId,
            CopilotReport report,
            CancellationToken cancellationToken)
        {
            try
            {
                var history = await _context.CopilotQueryHistories
                    .FirstOrDefaultAsync(item => item.Id == historyId, cancellationToken);

                if (history == null)
                    return;

                history.ResultJson = JsonSerializer.Serialize(report);
                await _context.SaveChangesAsync(cancellationToken);
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Failed to persist result data for query history {QueryId}", historyId);
            }
        }

        private static object? DeserializeResultData(string? resultJson)
        {
            if (string.IsNullOrWhiteSpace(resultJson))
                return null;

            try
            {
                using var document = JsonDocument.Parse(resultJson);
                if (!document.RootElement.TryGetProperty("Data", out var data) &&
                    !document.RootElement.TryGetProperty("data", out data))
                {
                    return null;
                }

                return data.Clone();
            }
            catch (JsonException)
            {
                return null;
            }
        }
    }
}
