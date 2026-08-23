using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.DTOs.SemanticLayer;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using System;
using System.Collections.Generic;
using System.Net.Http.Json;
using System.Text;

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

            // 👇 السطر السحري عشان ندي البايثون 10 دقايق يخلص براحته
            _httpClient.Timeout = TimeSpan.FromMinutes(10);

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

                // 👇 هنقرأ الرد كنص في كل الحالات عشان نعرف البايثون بيرجع إيه بالظبط
                var responseText = await response.Content.ReadAsStringAsync(cancellationToken);

                if (!response.IsSuccessStatusCode)
                {
                    return new AiSemanticDraftResult
                    {
                        IsSuccess = false,
                        ErrorMessage = $"HTTP {response.StatusCode} - AI_DETAILS: {responseText}"
                    };
                }

                // 👇 لو البايثون خلص ونجح (200 OK)، هنرجع اللي هو ولده جوه إيرور وهمي عشان نقراه في الـ Swagger
                return new AiSemanticDraftResult
                {
                    IsSuccess = false,
                    ErrorMessage = $"PYTHON_SUCCESS_BODY: {responseText}"
                };
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

                return new AiSemanticBaseResult { IsSuccess = true };
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

                return new AiSemanticBaseResult { IsSuccess = true };
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error validating draft with AI Runtime");
                return new AiSemanticBaseResult { IsSuccess = false, ErrorMessage = ex.Message };
            }
        }
    }
}