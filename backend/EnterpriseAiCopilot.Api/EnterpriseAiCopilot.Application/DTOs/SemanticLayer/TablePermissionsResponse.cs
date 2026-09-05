using System.Collections.Generic;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer;

public class TablePermissionUserResponse
{
    public string UserId { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public string DisplayName { get; set; } = string.Empty;
    public Dictionary<string, bool> Tables { get; set; } = new();
}

public class TablePermissionsResponse
{
    public string SemanticLayerId { get; set; } = string.Empty;
    public List<string> TableNames { get; set; } = new();
    public List<TablePermissionUserResponse> Users { get; set; } = new();
}
