using System.Collections.Generic;

namespace EnterpriseAiCopilot.Application.DTOs.Copilot;

public class SqlDebugResponse
{
    public string SemanticLayerId { get; set; } = string.Empty;
    public string Sql { get; set; } = string.Empty;
    public long TotalTimeMs { get; set; }
    public List<SqlDebugStage> Stages { get; set; } = new();
}

public class SqlDebugStage
{
    public string Name { get; set; } = string.Empty;
    public string Status { get; set; } = string.Empty;
    public long DurationMs { get; set; }
    public string? Message { get; set; }
    public object? Data { get; set; }
}
