using EnterpriseAiCopilot.Domain.Common;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Domain.Entities
{
    public class SemanticLayer : BaseEntity
    {
        public string Name { get; set; } = string.Empty;
        public string DatabaseName { get; set; } = string.Empty;
        public string Description { get; set; } = string.Empty;
        public bool IsActive { get; set; } = false;

        // Navigation Properties
        public ICollection<SemanticSourceFile> SourceFiles { get; set; } = new List<SemanticSourceFile>();
        public ICollection<SemanticRevision> Revisions { get; set; } = new List<SemanticRevision>();
    }
}
