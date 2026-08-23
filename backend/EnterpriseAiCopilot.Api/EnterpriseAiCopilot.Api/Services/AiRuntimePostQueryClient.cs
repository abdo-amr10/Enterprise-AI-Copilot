using System.Net.Http.Json;
using System.Text.Json;
using EnterpriseAiCopilot.Api.Contracts.Copilot;
using Microsoft.Extensions.Options;

namespace EnterpriseAiCopilot.Api.Services;

/// <summary>
/// The Backend-owned post-execution hop. SQL execution, authorization and RLS
/// finish before this client is called; this client only asks AI to format an
/// already-authorized result.
/// </summary>
public sealed class AiRuntimePostQueryClient
{
    private static readonly JsonSerializerOptions SerializerOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = true
    };

    private readonly HttpClient _httpClient;

    public AiRuntimePostQueryClient(HttpClient httpClient, IOptions<AiRuntimeOptions> options)
    {
        if (string.IsNullOrWhiteSpace(options.Value.BaseUrl))
        {
            throw new InvalidOperationException("AiRuntime:BaseUrl must be configured.");
        }

        _httpClient = httpClient;
    }

    public async Task<FormattedExecutionResult> FormatExecutionResultAsync(
        string question,
        ExecutionResult executionResult,
        CancellationToken cancellationToken = default)
    {
        var request = new PostQueryFormatRequest(question, executionResult);
        using var response = await _httpClient.PostAsJsonAsync(
            "internal/copilot/format-execution-result", request, SerializerOptions, cancellationToken);

        response.EnsureSuccessStatusCode();
        var formatted = await response.Content.ReadFromJsonAsync<FormattedExecutionResult>(SerializerOptions, cancellationToken);
        return formatted ?? throw new InvalidOperationException("AI Runtime returned an empty formatting response.");
    }
}
