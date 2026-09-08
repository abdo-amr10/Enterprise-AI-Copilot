using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Copilot
{
    public class ConversationMessage
    {
        public string Role { get; set; } = string.Empty;
        public string Content { get; set; } = string.Empty;
        public string? TurnId { get; set; }
        public string? UserQuestion { get; set; }
        public string? ResolvedQuestion { get; set; }
        public string? GeneratedSql { get; set; }
        public string? ExecutionResultSummary { get; set; }
        public string? ExecutionStatus { get; set; }
        public string? Classification { get; set; }
        public string? Timestamp { get; set; }
    }
}
