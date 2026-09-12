namespace EnterpriseAiCopilot.Application.DTOs.Copilot;

public class ConversationSummaryResponse
{
    public string ConversationId { get; set; } = string.Empty;
    public string? Title { get; set; }
    public string? LastQuestion { get; set; }
    public string CreatedAt { get; set; } = string.Empty;
    public string UpdatedAt { get; set; } = string.Empty;
}

public class ConversationTurnResponse
{
    public string QueryId { get; set; } = string.Empty;
    public string Question { get; set; } = string.Empty;
    public string? GeneratedSql { get; set; }
    public string? ResolvedQuestion { get; set; }
    public string Status { get; set; } = string.Empty;
    public string? ErrorMessage { get; set; }
    public long ExecutionTimeMs { get; set; }
    public string CreatedAt { get; set; } = string.Empty;
    public CopilotReport? Result { get; set; }
}

public class ConversationDetailsResponse
{
    public string ConversationId { get; set; } = string.Empty;
    public string? Title { get; set; }
    public string CreatedAt { get; set; } = string.Empty;
    public string UpdatedAt { get; set; } = string.Empty;
    public List<ConversationTurnResponse> Turns { get; set; } = new();
}
