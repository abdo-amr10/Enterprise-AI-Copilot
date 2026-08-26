using System.Net.Http.Json;
using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.DTOs.Copilot;
using Microsoft.Extensions.Configuration;

namespace EnterpriseAiCopilot.Infrastructure.ExternalServices;

public class AiResultFormatterHttpClient : IAiResultFormatterClient
{
    private readonly HttpClient _httpClient;
    private readonly IConfiguration _configuration;

    public AiResultFormatterHttpClient(HttpClient httpClient, IConfiguration configuration)
    {
        _httpClient = httpClient;
        _configuration = configuration;

        var baseUrl = _configuration["AiRuntime:BaseUrl"];
        if (!string.IsNullOrWhiteSpace(baseUrl))
            _httpClient.BaseAddress = new Uri(baseUrl);
    }

    public async Task<CopilotReport> FormatExecutionResultAsync(
        string question,
        object executionResult,
        CancellationToken cancellationToken = default)
    {
        var payload = new
        {
            question = question,
            executionResult = executionResult
        };

        var response = await _httpClient.PostAsJsonAsync(
            "internal/copilot/format-execution-result",
            payload,
            cancellationToken);

        response.EnsureSuccessStatusCode();

        var aiResponse = await response.Content.ReadFromJsonAsync<AiFormatterResponse>(cancellationToken: cancellationToken);

        return new CopilotReport
        {
            TextSummary = aiResponse?.Text ?? "Here is the information you requested.",
            PresentationType = aiResponse?.PresentationType ?? "Table",
            Data = executionResult
        };
    }

    private class AiFormatterResponse
    {
        public string? Status { get; set; }
        public string? PresentationType { get; set; }
        public string? Text { get; set; }
        public int RowCount { get; set; }
    }
}