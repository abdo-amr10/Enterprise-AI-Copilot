using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer
{
    public class UploadDataSourcesRequest
    {
        [FromForm(Name = "name")]
        public string Name { get; set; } = string.Empty;

        [FromForm(Name = "description")]
        public string Description { get; set; } = string.Empty;

        [FromForm(Name = "schema")]
        public IFormFile SchemaFile { get; set; } = null!;

        [FromForm(Name = "documentation")]
        public IFormFile? DocumentationFile { get; set; }

        [FromForm(Name = "glossary")]
        public IFormFile? GlossaryFile { get; set; }

        [FromForm(Name = "sampleData")]
        public IFormFile? SampleDataFile { get; set; }
    }
}
