using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer
{
    public class ReviewRevisionRequest
    {
        public string SemanticLayerId { get; set; } = string.Empty;
        public string RevisionId { get; set; } = string.Empty;
        public string Decision { get; set; } = string.Empty; 
        public string? Comments { get; set; }
    }
}
