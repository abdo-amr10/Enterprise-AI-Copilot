using EnterpriseAiCopilot.Domain.Common;
using System;

namespace EnterpriseAiCopilot.Domain.Entities
{
    public class SemanticRevision : BaseEntity
    {
        public int VersionNumber { get; set; }
        public string ContentJson { get; set; } = string.Empty;

        public string Status { get; set; } = "PendingReview";

        public string? ReviewedBy { get; set; }
        public DateTime? ReviewedAt { get; set; }
        public string? ReviewNotes { get; set; }

        public string RegenerationType { get; set; } = string.Empty;
        public int RegeneratedObjectsCount { get; set; }

        public Guid SemanticLayerId { get; set; }
        public SemanticLayer? SemanticLayer { get; set; }
    }
}