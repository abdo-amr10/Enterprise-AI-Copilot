using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer
{
    public class ReviewRevisionResponse
    {
        public string SemanticLayerId { get; set; } = string.Empty;
        public string RevisionId { get; set; } = string.Empty;
        public string Status { get; set; } = string.Empty;

        public string? Version { get; set; }
        public string? Comments { get; set; }

        public string? ApprovedBy { get; set; }
        public string? ApprovedAt { get; set; }

        public string? RejectedBy { get; set; }
        public string? RejectedAt { get; set; }
    }
}
