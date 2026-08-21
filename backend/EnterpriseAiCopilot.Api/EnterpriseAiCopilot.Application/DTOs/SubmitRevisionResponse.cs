using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs
{
    public class SubmitRevisionResponse
    {
        public string Status { get; set; } = string.Empty;
        public string SemanticLayerId { get; set; } = string.Empty;
        public string RevisionId { get; set; } = string.Empty;
        public string Message { get; set; } = string.Empty;
    }
}
