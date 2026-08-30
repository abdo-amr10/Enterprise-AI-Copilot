using EnterpriseAiCopilot.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.Common.Interfaces
{
    public interface IApplicationDbContext
    {
        DbSet<User> Users { get; }
        DbSet<SemanticLayer> SemanticLayers { get; }
        DbSet<SemanticSourceFile> SemanticSourceFiles { get; }
        DbSet<SemanticRevision> SemanticRevisions { get; }
        DbSet<CopilotQueryHistory> CopilotQueryHistories { get; }
        DbSet<AllowedTable> AllowedTables { get; }
        DbSet<UserTablePermission> UserTablePermissions { get; }
        DbSet<AuditLog> AuditLogs { get; }
        Task<int> SaveChangesAsync(CancellationToken cancellationToken = default);
    }
}
