using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.EntityFrameworkCore;
using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.Common.Models;
using EnterpriseAiCopilot.Application.DTOs.Audit;
using EnterpriseAiCopilot.Domain.Entities;
using System;

namespace EnterpriseAiCopilot.Application.Services
{
    public class AuditService : IAuditService
    {
        private readonly IApplicationDbContext _context;

        public AuditService(IApplicationDbContext context)
        {
            _context = context;
        }

        public async Task<Result<AuditLogResponse>> GetAuditLogsAsync(AuditLogQuery query, CancellationToken cancellationToken = default)
        {
            var auditQuery = _context.AuditLogs.AsNoTracking().AsQueryable();

            if (!string.IsNullOrWhiteSpace(query.Action))
                auditQuery = auditQuery.Where(a => a.Action == query.Action);

            if (!string.IsNullOrWhiteSpace(query.UserId))
                auditQuery = auditQuery.Where(a => a.UserId == query.UserId);

            if (query.From.HasValue)
                auditQuery = auditQuery.Where(a => a.Timestamp >= query.From.Value);

            if (query.To.HasValue)
                auditQuery = auditQuery.Where(a => a.Timestamp <= query.To.Value);

            var logs = await auditQuery
                .OrderByDescending(a => a.Timestamp)
                .Select(a => new AuditLogItemResponse
                {
                    EventId = a.EventId,
                    Action = a.Action,
                    UserId = a.UserId,
                    ResourceId = a.ResourceId,
                    Status = a.Status,
                    Timestamp = a.Timestamp.ToString("yyyy-MM-ddTHH:mm:ssZ")
                })
                .ToListAsync(cancellationToken);

            return Result<AuditLogResponse>.Success(new AuditLogResponse { Items = logs });
        }

        public async Task LogEventAsync(string action, string userId, string status, string? resourceId = null, CancellationToken cancellationToken = default)
        {
            var auditLog = new AuditLog
            {
                Action = action,
                UserId = userId,
                Status = status,
                ResourceId = resourceId,
                Timestamp = DateTime.UtcNow
            };

            _context.AuditLogs.Add(auditLog);
            await _context.SaveChangesAsync(cancellationToken);
        }
    }
}