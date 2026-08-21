using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer
{
    public class SemanticSources
    {
        public string? SchemaFileId { get; set; }
        public string? DocumentationFileId { get; set; }
        public string? GlossaryFileId { get; set; }
        public string? SampleDataFileId { get; set; }
    }
}
