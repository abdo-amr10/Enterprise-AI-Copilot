using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Domain.Entities
{
    public class CopilotQueryHistory
    {
        public Guid Id { get; set; } = Guid.NewGuid();

        public string UserId { get; set; } = string.Empty;

        public string UserPrompt { get; set; } = string.Empty;
        public string BranchId { get; set; } = string.Empty;
        public string? GeneratedSql { get; set; }

        public Guid SemanticLayerId { get; set; }
        public virtual SemanticLayer? SemanticLayer { get; set; }

        public string Status { get; set; } = string.Empty;

        public string? ErrorMessage { get; set; }

        public long ExecutionTimeMs { get; set; }

        public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    }
}
