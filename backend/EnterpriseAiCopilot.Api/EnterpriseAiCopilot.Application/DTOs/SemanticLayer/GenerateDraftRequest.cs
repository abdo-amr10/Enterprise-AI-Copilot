using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer
{
    public class GenerateDraftRequest
    {
        public string SemanticLayerId { get; set; } = string.Empty;
        public string TriggerType { get; set; } = string.Empty;
        public SourceFileIds SourceFileIds { get; set; } = new();

        public string? BaseRevisionId { get; set; }
        public List<AffectedObject>? AffectedObjects { get; set; }
    }
}
