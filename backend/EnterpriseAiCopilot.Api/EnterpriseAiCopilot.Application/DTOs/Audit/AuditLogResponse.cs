using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Audit
{
    public class AuditLogResponse
    {
        public IEnumerable<AuditLogItemResponse> Items { get; set; } = new List<AuditLogItemResponse>();
    }
}
