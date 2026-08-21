using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer
{
    public class GenerateDraftResponse
    {
        public string Status { get; set; } = string.Empty;
        public string SemanticLayerId { get; set; } = string.Empty;
        public string RevisionId { get; set; } = string.Empty;

        public string? BaseRevisionId { get; set; }

        public int RegeneratedObjectsCount { get; set; }
        public string BuildTimestamp { get; set; } = string.Empty;
        public string LastRegenerationType { get; set; } = string.Empty;

        public List<AffectedObject>? AffectedObjects { get; set; }
    }
}
