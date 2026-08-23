using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer
{
    public class AiSemanticDraftResult : AiSemanticBaseResult
    {
        public string? ContentJson { get; set; }
        public int RegeneratedObjectsCount { get; set; }
    }
}
