using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Audit
{
    public class AuditLogItemResponse
    {
        public string EventId { get; set; } = string.Empty;
        public string Action { get; set; } = string.Empty;
        public string UserId { get; set; } = string.Empty;
        public string? ResourceId { get; set; }
        public string Status { get; set; } = string.Empty;
        public string Timestamp { get; set; } = string.Empty;
    }
}
