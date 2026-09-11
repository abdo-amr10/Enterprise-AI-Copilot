namespace EnterpriseAiCopilot.Application.DTOs.Copilot;

public class SqlDebugRequest
{
    public string SemanticLayerId { get; set; } = string.Empty;
    public string Sql { get; set; } = string.Empty;
}
