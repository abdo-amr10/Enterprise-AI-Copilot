namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer;

public sealed class RlsPolicyRequest
{
    public bool Enabled { get; set; } = true;
    public string UserValueField { get; set; } = "BranchId";
    public string ScopeParameter { get; set; } = "@UserScopeId";
    public BranchMappingRequest? BranchMapping { get; set; }
    public List<RlsRuleRequest> Rules { get; set; } = new();
}

public sealed class BranchMappingRequest
{
    public string Table { get; set; } = string.Empty;
    public string IdColumn { get; set; } = string.Empty;
    public string? NameColumn { get; set; }
}

public sealed class RlsRuleRequest
{
    public string Table { get; set; } = string.Empty;
    public string? JoinTable { get; set; }
    public string? JoinFromColumn { get; set; }
    public string? JoinToColumn { get; set; }
    public string ScopeColumn { get; set; } = string.Empty;
    public string Type { get; set; } = "direct";
}
