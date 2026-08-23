using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Copilot
{
    public class AskCopilotResponse
    {
        public string QueryId { get; set; } = string.Empty;
        public string Status { get; set; } = string.Empty;
        public CopilotReport? Report { get; set; }
        public string? ErrorCode { get; set; }
        public string? Message { get; set; }
    }
}
