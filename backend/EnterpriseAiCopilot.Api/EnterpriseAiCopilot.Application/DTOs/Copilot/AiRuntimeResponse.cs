using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Copilot
{
    public class AiRuntimeResponse
    {
        public bool IsSuccess { get; set; }
        public string? GeneratedSql { get; set; }
        public string? TextSummary { get; set; }
        public string PresentationType { get; set; } = "DataTable";
        public string? ErrorMessage { get; set; }
    }
}
