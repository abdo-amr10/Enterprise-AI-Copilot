namespace EnterpriseAiCopilot.Api.Contracts.Copilot;

/// <summary>Connection settings for the private AI Runtime service.</summary>
public sealed class AiRuntimeOptions
{
    public const string SectionName = "AiRuntime";

    /// <example>http://localhost:8000</example>
    public string BaseUrl { get; init; } = string.Empty;
    public int TimeoutSeconds { get; init; } = 30;
}
