using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Copilot
{
    public class AskCopilotRequest
    {
        public string Question { get; set; } = string.Empty;
        public string? ConversationId { get; set; }
        public List<ConversationMessage> Conversation { get; set; } = new();
    }
}
