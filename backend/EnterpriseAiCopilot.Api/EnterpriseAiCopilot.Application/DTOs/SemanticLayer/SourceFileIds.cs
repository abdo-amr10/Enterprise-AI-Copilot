using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer
{
    public class SourceFileIds
    {
        public string? Schema { get; set; }
        public string? Documentation { get; set; }
        public string? Glossary { get; set; }
        public string? SampleData { get; set; }
    }
}
