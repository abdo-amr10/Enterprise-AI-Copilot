using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Copilot
{
    public class QueryHistoryItemResponse
    {
        public string QueryId { get; set; } = string.Empty;
        public string Question { get; set; } = string.Empty;
        public string Status { get; set; } = string.Empty;
        public string CreatedAt { get; set; } = string.Empty;
    }
}
