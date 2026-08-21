using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs
{
    public class RetrieveSourceFileResponse
    {
        public string Status { get; set; } = "Success"; 
        public string FileId { get; set; } = string.Empty;
        public string FileType { get; set; } = string.Empty;
        public string FileName { get; set; } = string.Empty;

        public object Content { get; set; } = null!;
    }
}
