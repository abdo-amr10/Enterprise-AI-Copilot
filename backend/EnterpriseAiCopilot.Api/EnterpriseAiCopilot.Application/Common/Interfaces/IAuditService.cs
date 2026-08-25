using EnterpriseAiCopilot.Application.Common.Models;
using EnterpriseAiCopilot.Application.DTOs.Audit;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.Common.Interfaces
{
    public interface IAuditService
    {
        Task<Result<AuditLogResponse>> GetAuditLogsAsync(AuditLogQuery query, CancellationToken cancellationToken = default);
        Task LogEventAsync(string action, string userId, string status, string? resourceId = null, CancellationToken cancellationToken = default);
    }
}
