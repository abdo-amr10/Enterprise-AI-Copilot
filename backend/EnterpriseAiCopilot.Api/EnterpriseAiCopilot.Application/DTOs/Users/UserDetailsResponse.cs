namespace EnterpriseAiCopilot.Application.DTOs.Users;

public sealed class UserDetailsResponse
{
    public string UserId { get; set; } = string.Empty;
    public string FirstName { get; set; } = string.Empty;
    public string LastName { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public string Role { get; set; } = string.Empty;
    public string? BranchId { get; set; }
    public string? BranchName { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime? LastModifiedAt { get; set; }
    public int ConversationCount { get; set; }
    public int QueryCount { get; set; }
    public List<UserTablePermissionResponse> TablePermissions { get; set; } = new();
}

public sealed class PublicUserResponse
{
    public string UserId { get; set; } = string.Empty;
    public string FirstName { get; set; } = string.Empty;
    public string LastName { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public string Role { get; set; } = string.Empty;
    public string? BranchId { get; set; }
    public string? BranchName { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime? LastModifiedAt { get; set; }
}

public sealed class UserTablePermissionResponse
{
    public string SemanticLayerId { get; set; } = string.Empty;
    public string TableName { get; set; } = string.Empty;
    public bool IsAllowed { get; set; }
}
