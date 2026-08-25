using EnterpriseAiCopilot.Domain.Common;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Domain.Entities
{
    public class AuditLog : BaseEntity
    {
        public string EventId { get; set; } = Guid.NewGuid().ToString("N");
        public string Action { get; set; } = string.Empty;
        public string UserId { get; set; } = string.Empty;
        public string? ResourceId { get; set; }
        public string Status { get; set; } = string.Empty;
        public DateTime Timestamp { get; set; } = DateTime.UtcNow;
    }
}
