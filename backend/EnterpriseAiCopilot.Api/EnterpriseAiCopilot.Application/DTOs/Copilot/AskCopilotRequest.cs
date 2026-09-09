using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Copilot
{
    public class AskCopilotRequest
    {
        public string Question { get; set; } = string.Empty;
        public string? ConversationId { get; set; }
        public string? TenantId { get; set; }
        public string? UserId { get; set; }
        public string? BranchId { get; set; }
        public string? SemanticRevisionId { get; set; }
        public string? SchemaVersion { get; set; }
        public object? LastResultMetadata { get; set; }
        public List<ConversationMessage> Conversation { get; set; } = new();
    }
}
