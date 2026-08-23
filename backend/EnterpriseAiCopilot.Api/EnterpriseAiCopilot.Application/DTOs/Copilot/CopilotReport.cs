using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Copilot
{
    public class CopilotReport
    {
        public string TextSummary { get; set; } = string.Empty;
        public string PresentationType { get; set; } = string.Empty;
        public object? Data { get; set; }
    }
}
