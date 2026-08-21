using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer
{
    public class SemanticRevisionContent
    {
        public List<object> Entities { get; set; } = new();
        public List<object> Relationships { get; set; } = new();
        public List<object> Measures { get; set; } = new();
        public List<object> Dimensions { get; set; } = new();
        public List<object> BusinessRules { get; set; } = new();
        public List<object> ValidationIssues { get; set; } = new();
    }
}
