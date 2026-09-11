namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer;

public sealed class DatabaseMetadataResponse
{
    public string SemanticLayerId { get; set; } = string.Empty;
    public string DatabaseName { get; set; } = string.Empty;
    public DateTime SyncedAtUtc { get; set; }
    public object Metadata { get; set; } = new();
}
