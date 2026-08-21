using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer
{
    public class UpsertSourceFileRequest
    {
        [FromForm(Name = "file")]
        public IFormFile File { get; set; } = null!;

        [FromForm(Name = "fileType")]
        public string FileType { get; set; } = string.Empty;
    }
}