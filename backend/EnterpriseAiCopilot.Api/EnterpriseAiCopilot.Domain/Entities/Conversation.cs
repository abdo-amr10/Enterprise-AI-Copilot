using EnterpriseAiCopilot.Domain.Common;

namespace EnterpriseAiCopilot.Domain.Entities;

public class Conversation : BaseEntity
{
    public string UserId { get; set; } = string.Empty;
    public string BranchId { get; set; } = string.Empty;
    public Guid SemanticLayerId { get; set; }
    public string? Title { get; set; }
    public bool IsArchived { get; set; }
    public virtual SemanticLayer? SemanticLayer { get; set; }
    public virtual ICollection<CopilotQueryHistory> QueryHistories { get; set; } = new List<CopilotQueryHistory>();
}
