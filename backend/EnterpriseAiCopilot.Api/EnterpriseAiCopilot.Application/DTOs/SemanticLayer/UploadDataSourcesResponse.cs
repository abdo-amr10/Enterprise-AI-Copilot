using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer
{
    public class UploadDataSourcesResponse
    {
        public string Status { get; set; } = string.Empty;
        public string Message { get; set; } = string.Empty;
        public string SemanticLayerId { get; set; } = string.Empty;
        public string Name { get; set; } = string.Empty;
        public string Description { get; set; } = string.Empty;

        public SemanticSources Sources { get; set; } = new();

        public bool HasDocumentation { get; set; }
        public bool HasGlossary { get; set; }
        public bool HasSampleData { get; set; }
    }
}
