using System;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.DTOs.Copilot;

namespace EnterpriseAiCopilot.Infrastructure.ExternalServices
{
    public class AiRuntimeHttpClient : IAiRuntimeClient
    {
        private readonly HttpClient _httpClient;
        private readonly IConfiguration _configuration;
        private readonly ILogger<AiRuntimeHttpClient> _logger;

        public AiRuntimeHttpClient(
            HttpClient httpClient,
            IConfiguration configuration,
            ILogger<AiRuntimeHttpClient> logger)
        {
            _httpClient = httpClient;
            _configuration = configuration;
            _logger = logger;

            var timeoutSeconds = int.TryParse(
                _configuration["AiRuntime:TimeoutSeconds"],
                out var configuredTimeoutSeconds)
                && configuredTimeoutSeconds > 0
                    ? configuredTimeoutSeconds
                    : 600;
            _httpClient.Timeout = TimeSpan.FromSeconds(timeoutSeconds);

            var baseUrl = _configuration["AiRuntime:BaseUrl"];
            if (!string.IsNullOrWhiteSpace(baseUrl))
            {
                _httpClient.BaseAddress = new Uri(baseUrl);
            }
        }

        public async Task<AiRuntimeResponse> ProcessQuestionAsync(AskCopilotRequest request, CancellationToken cancellationToken = default)
        {
            if (request == null || string.IsNullOrWhiteSpace(request.Question))
            {
                return new AiRuntimeResponse
                {
                    IsSuccess = false,
                    ErrorMessage = "VALIDATION_ERROR: Question cannot be null or empty."
                };
            }

            try
            {
                var endpoint = _configuration["AiRuntime:ProcessEndpoint"] ?? "internal/copilot/text-to-sql";

                var payload = new
                {
                    question = request.Question,
                    conversation = request.Conversation
                };

                var response = await _httpClient.PostAsJsonAsync(endpoint, payload, cancellationToken);

                if (!response.IsSuccessStatusCode)
                {
                    var errorContent = await response.Content.ReadAsStringAsync(cancellationToken);
                    _logger.LogError("AI Runtime returned non-success status code {StatusCode}: {Error}", response.StatusCode, errorContent);

                    return new AiRuntimeResponse
                    {
                        IsSuccess = false,
                        ErrorMessage = $"AI_RUNTIME_ERROR: External AI service failed with status code {response.StatusCode}."
                    };
                }

                var aiResponse = await response.Content.ReadFromJsonAsync<AiRuntimeResponse>(cancellationToken: cancellationToken);

                if (aiResponse == null)
                {
                    return new AiRuntimeResponse
                    {
                        IsSuccess = false,
                        ErrorMessage = "AI_RUNTIME_ERROR: Received empty response from AI runtime."
                    };
                }

                return aiResponse;
            }
            catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
            {
                _logger.LogError(
                    "AI Runtime request timed out after {TimeoutSeconds} seconds.",
                    _httpClient.Timeout.TotalSeconds);
                return new AiRuntimeResponse
                {
                    IsSuccess = false,
                    ErrorMessage = "AI_RUNTIME_ERROR: AI runtime request timed out."
                };
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (HttpRequestException ex)
            {
                _logger.LogError(ex, "Network or HTTP error while communicating with AI Runtime.");
                return new AiRuntimeResponse
                {
                    IsSuccess = false,
                    ErrorMessage = "AI_RUNTIME_ERROR: Failed to connect to AI runtime service."
                };
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Unexpected error occurred while processing AI runtime request.");
                return new AiRuntimeResponse
                {
                    IsSuccess = false,
                    ErrorMessage = "AI_RUNTIME_ERROR: An unexpected error occurred."
                };
            }
        }
    }
}
