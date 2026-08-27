using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.DTOs.SemanticLayer;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using System;
using System.Collections.Generic;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace EnterpriseAiCopilot.Infrastructure.ExternalServices
{
    public class AiSemanticHttpClient : IAiSemanticClient
    {
        private readonly HttpClient _httpClient;
        private readonly ILogger<AiSemanticHttpClient> _logger;

        public AiSemanticHttpClient(HttpClient httpClient, IConfiguration configuration, ILogger<AiSemanticHttpClient> logger)
        {
            _httpClient = httpClient;
            _logger = logger;

            _httpClient.Timeout = TimeSpan.FromMinutes(30);

            var baseUrl = configuration["AiRuntime:BaseUrl"];
            if (!string.IsNullOrWhiteSpace(baseUrl))
            {
                _httpClient.BaseAddress = new Uri(baseUrl);
            }
        }

        public async Task<AiSemanticDraftResult> GenerateDraftAsync(GenerateDraftRequest request, CancellationToken cancellationToken = default)
        {
            try
            {
                var response = await _httpClient.PostAsJsonAsync("internal/semantic/generate-draft", request, cancellationToken);
                var responseText = await response.Content.ReadAsStringAsync(cancellationToken);

                if (!response.IsSuccessStatusCode)
                {
                    return new AiSemanticDraftResult
                    {
                        IsSuccess = false,
                        ErrorMessage = $"HTTP {response.StatusCode} - AI_DETAILS: {responseText}"
                    };
                }

                using var document = JsonDocument.Parse(responseText);
                var root = document.RootElement;

                bool isSuccess = true;
                string? errorMessage = null;

                if (root.TryGetProperty("status", out var statusProp) && statusProp.ValueKind == JsonValueKind.String)
                {
                    if (!statusProp.GetString()!.Equals("Success", StringComparison.OrdinalIgnoreCase))
                    {
                        isSuccess = false;
                    }
                }

                if (root.TryGetProperty("errorMessage", out var errorProp) && errorProp.ValueKind == JsonValueKind.String)
                {
                    errorMessage = errorProp.GetString();
                    if (!string.IsNullOrEmpty(errorMessage)) isSuccess = false;
                }

                if (!isSuccess)
                {
                    return new AiSemanticDraftResult
                    {
                        IsSuccess = false,
                        ErrorMessage = errorMessage ?? "AI Runtime indicated failure without providing an error message."
                    };
                }

                string contentJson = "{}";
                if (root.TryGetProperty("data", out var dataProp))
                {
                    if (dataProp.TryGetProperty("draftJson", out var draftProp))
                        contentJson = draftProp.ValueKind == JsonValueKind.String ? draftProp.GetString()! : draftProp.GetRawText();
                    else
                        contentJson = dataProp.GetRawText();
                }
                else if (root.TryGetProperty("draftJson", out var draftPropDirect))
                {
                    contentJson = draftPropDirect.ValueKind == JsonValueKind.String ? draftPropDirect.GetString()! : draftPropDirect.GetRawText();
                }
                else if (root.TryGetProperty("contentJson", out var contentPropDirect))
                {
                    contentJson = contentPropDirect.ValueKind == JsonValueKind.String ? contentPropDirect.GetString()! : contentPropDirect.GetRawText();
                }
                else
                {
                    contentJson = responseText;
                }

                int regeneratedCount = 0;
                if (root.TryGetProperty("regeneratedObjectsCount", out var regCountProp) && regCountProp.ValueKind == JsonValueKind.Number)
                {
                    regeneratedCount = regCountProp.GetInt32();
                }

                return new AiSemanticDraftResult
                {
                    IsSuccess = true,
                    ContentJson = contentJson,
                    RegeneratedObjectsCount = regeneratedCount
                };
            }
            catch (JsonException ex)
            {
                _logger.LogError(ex, "Failed to parse AI response JSON.");
                return new AiSemanticDraftResult { IsSuccess = false, ErrorMessage = "Invalid JSON response from AI Runtime." };
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error generating draft from AI Runtime");
                return new AiSemanticDraftResult { IsSuccess = false, ErrorMessage = ex.Message };
            }
        }

        public async Task<AiSemanticBaseResult> ReviewDraftAsync(string revisionId, string decision, string? comments, CancellationToken cancellationToken = default)
        {
            try
            {
                var payload = new { revisionId, decision, comments };
                var response = await _httpClient.PostAsJsonAsync("internal/semantic/review", payload, cancellationToken);

                if (!response.IsSuccessStatusCode)
                    return new AiSemanticBaseResult { IsSuccess = false, ErrorMessage = $"HTTP {response.StatusCode}" };

                return await ReadBaseResultAsync(response, "review", cancellationToken);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error submitting review to AI Runtime");
                return new AiSemanticBaseResult { IsSuccess = false, ErrorMessage = ex.Message };
            }
        }

        public async Task<AiSemanticBaseResult> ValidateDraftAsync(string revisionId, CancellationToken cancellationToken = default)
        {
            try
            {
                var payload = new { revisionId };
                var response = await _httpClient.PostAsJsonAsync("internal/semantic/validate", payload, cancellationToken);

                if (!response.IsSuccessStatusCode)
                    return new AiSemanticBaseResult { IsSuccess = false, ErrorMessage = $"HTTP {response.StatusCode}" };

                return await ReadBaseResultAsync(response, "validation", cancellationToken);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error validating draft with AI Runtime");
                return new AiSemanticBaseResult { IsSuccess = false, ErrorMessage = ex.Message };
            }
        }

        private static async Task<AiSemanticBaseResult> ReadBaseResultAsync(
            HttpResponseMessage response,
            string operation,
            CancellationToken cancellationToken)
        {
            var responseText = await response.Content.ReadAsStringAsync(cancellationToken);

            if (string.IsNullOrWhiteSpace(responseText))
            {
                return new AiSemanticBaseResult
                {
                    IsSuccess = false,
                    ErrorMessage = $"AI Runtime returned an empty {operation} response."
                };
            }

            using var document = JsonDocument.Parse(responseText);
            var root = document.RootElement;

            if (root.TryGetProperty("isSuccess", out var successProperty) &&
                successProperty.ValueKind == JsonValueKind.False)
            {
                return new AiSemanticBaseResult
                {
                    IsSuccess = false,
                    ErrorMessage = ReadErrorMessage(root) ?? $"AI Runtime rejected {operation}."
                };
            }

            if (root.TryGetProperty("errorMessage", out var errorProperty) &&
                errorProperty.ValueKind == JsonValueKind.String &&
                !string.IsNullOrWhiteSpace(errorProperty.GetString()))
            {
                return new AiSemanticBaseResult
                {
                    IsSuccess = false,
                    ErrorMessage = errorProperty.GetString()
                };
            }

            if (root.TryGetProperty("status", out var statusProperty) &&
                statusProperty.ValueKind == JsonValueKind.String)
            {
                var status = statusProperty.GetString();
                if (string.Equals(status, "Failed", StringComparison.OrdinalIgnoreCase) ||
                    string.Equals(status, "Error", StringComparison.OrdinalIgnoreCase) ||
                    string.Equals(status, "Rejected", StringComparison.OrdinalIgnoreCase) && operation == "validation")
                {
                    return new AiSemanticBaseResult
                    {
                        IsSuccess = false,
                        ErrorMessage = ReadErrorMessage(root) ?? $"AI Runtime rejected {operation}."
                    };
                }

                var validStatus = string.Equals(status, "Success", StringComparison.OrdinalIgnoreCase) ||
                                  string.Equals(status, "Approved", StringComparison.OrdinalIgnoreCase) ||
                                  string.Equals(status, "Rejected", StringComparison.OrdinalIgnoreCase) && operation == "review" ||
                                  string.Equals(status, "Valid", StringComparison.OrdinalIgnoreCase) ||
                                  string.Equals(status, "Validated", StringComparison.OrdinalIgnoreCase);

                if (!validStatus)
                {
                    return new AiSemanticBaseResult
                    {
                        IsSuccess = false,
                        ErrorMessage = $"AI Runtime returned an invalid {operation} status."
                    };
                }
            }
            else if (!root.TryGetProperty("isSuccess", out successProperty) ||
                     successProperty.ValueKind != JsonValueKind.True)
            {
                return new AiSemanticBaseResult
                {
                    IsSuccess = false,
                    ErrorMessage = $"AI Runtime returned an invalid {operation} response contract."
                };
            }

            return new AiSemanticBaseResult { IsSuccess = true };
        }

        private static string? ReadErrorMessage(JsonElement root)
        {
            if (root.TryGetProperty("errorMessage", out var errorProperty) &&
                errorProperty.ValueKind == JsonValueKind.String)
            {
                return errorProperty.GetString();
            }

            if (root.TryGetProperty("message", out var messageProperty) &&
                messageProperty.ValueKind == JsonValueKind.String)
            {
                return messageProperty.GetString();
            }

            return null;
        }
    }
}
