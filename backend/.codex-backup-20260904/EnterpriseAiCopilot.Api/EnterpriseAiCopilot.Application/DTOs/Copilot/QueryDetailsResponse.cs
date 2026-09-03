using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Copilot
{
    public class QueryDetailsResponse
    {
        public string QueryId { get; set; } = string.Empty;
        public string Question { get; set; } = string.Empty;
        public string Status { get; set; } = string.Empty;
        public string CreatedAt { get; set; } = string.Empty;
        public string? GeneratedSql { get; set; }
        public long ExecutionTimeMs { get; set; }
        public string? ErrorMessage { get; set; }
        public string? SemanticLayerId { get; set; }
        public CopilotReportSummary? Result { get; set; }
    }
}
