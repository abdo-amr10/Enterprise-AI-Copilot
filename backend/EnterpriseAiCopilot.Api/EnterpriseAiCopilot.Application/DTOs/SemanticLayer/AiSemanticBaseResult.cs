using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer
{
    public class AiSemanticBaseResult
    {
        public bool IsSuccess { get; set; }
        public string? ErrorMessage { get; set; }
    }
}
