using EnterpriseAiCopilot.Domain.Common;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Domain.Entities
{
    public class AllowedTable : BaseEntity
    {
        public string TableName { get; set; } = string.Empty;
        public bool IsAllowed { get; set; } = true; 
        public Guid SemanticLayerId { get; set; } 
    }
}
