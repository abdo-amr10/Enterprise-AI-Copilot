using EnterpriseAiCopilot.Domain.Common;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Domain.Entities
{
    public class SemanticSourceFile : BaseEntity
    {
        public string FileName { get; set; } = string.Empty;
        public string FileType { get; set; } = string.Empty; 
        public long FileSize { get; set; }
        public string StoragePath { get; set; } = string.Empty;
        public string UploadedBy { get; set; } = string.Empty;

        public Guid SemanticLayerId { get; set; }
        public SemanticLayer? SemanticLayer { get; set; }
    }
}
