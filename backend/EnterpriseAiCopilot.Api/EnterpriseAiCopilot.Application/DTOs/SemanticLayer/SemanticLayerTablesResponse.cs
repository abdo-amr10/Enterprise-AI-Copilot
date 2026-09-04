using System.Collections.Generic;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer;

public class SemanticLayerTableResponse
{
    public string TableName { get; set; } = string.Empty;
    public bool IsAllowed { get; set; }
}

public class SemanticLayerTablesResponse
{
    public string SemanticLayerId { get; set; } = string.Empty;
    public List<SemanticLayerTableResponse> Tables { get; set; } = new();
}
