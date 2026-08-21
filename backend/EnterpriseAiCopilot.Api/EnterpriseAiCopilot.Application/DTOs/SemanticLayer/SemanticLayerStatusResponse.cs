using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer
{
    public class SemanticLayerStatusResponse
    {
        public string SemanticLayerId { get; set; } = string.Empty;
        public string Status { get; set; } = string.Empty;
        public string Version { get; set; } = string.Empty;
        public string RevisionId { get; set; } = string.Empty;
        public string BuildTimestamp { get; set; } = string.Empty;
        public string LastRegenerationType { get; set; } = string.Empty;
    }
}
