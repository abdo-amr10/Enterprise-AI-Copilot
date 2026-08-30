using EnterpriseAiCopilot.Domain.Common;

namespace EnterpriseAiCopilot.Domain.Entities;

public class UserTablePermission : BaseEntity
{
    public Guid UserId { get; set; }
    public Guid SemanticLayerId { get; set; }
    public string TableName { get; set; } = string.Empty;
    public bool IsAllowed { get; set; }

    public User User { get; set; } = null!;
    public SemanticLayer SemanticLayer { get; set; } = null!;
}
