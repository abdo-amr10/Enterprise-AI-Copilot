using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Domain.Common;
using EnterpriseAiCopilot.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Infrastructure.Persistence
{
    public class ApplicationDbContext : DbContext, IApplicationDbContext
    {
        private readonly ICurrentUserService _currentUserService;

        public ApplicationDbContext(
            DbContextOptions<ApplicationDbContext> options,
            ICurrentUserService currentUserService) : base(options)
        {
            _currentUserService = currentUserService;
        }

        public DbSet<User> Users => Set<User>();
        public DbSet<SemanticLayer> SemanticLayers => Set<SemanticLayer>();
        public DbSet<SemanticSourceFile> SemanticSourceFiles => Set<SemanticSourceFile>();
        public DbSet<SemanticRevision> SemanticRevisions => Set<SemanticRevision>();
        public DbSet<CopilotQueryHistory> CopilotQueryHistories => Set<CopilotQueryHistory>();
        public DbSet<AllowedTable> AllowedTables => Set<AllowedTable>();
        public DbSet<UserTablePermission> UserTablePermissions => Set<UserTablePermission>();
        public DbSet<AuditLog> AuditLogs => Set<AuditLog>();
        protected override void OnModelCreating(ModelBuilder modelBuilder)
        {
            modelBuilder.ApplyConfigurationsFromAssembly(typeof(ApplicationDbContext).Assembly);
            base.OnModelCreating(modelBuilder);
        }

        public override int SaveChanges(bool acceptAllChangesOnSuccess)
        {
            ApplyAuditFields();
            return base.SaveChanges(acceptAllChangesOnSuccess);
        }

        public override Task<int> SaveChangesAsync(
            bool acceptAllChangesOnSuccess,
            CancellationToken cancellationToken = default)
        {
            ApplyAuditFields();
            return base.SaveChangesAsync(acceptAllChangesOnSuccess, cancellationToken);
        }

        private void ApplyAuditFields()
        {
            var actorId = _currentUserService.UserId ?? "SYSTEM";
            var now = DateTime.UtcNow;

            foreach (var entry in ChangeTracker.Entries<BaseEntity>())
            {
                if (entry.State == EntityState.Added)
                {
                    if (entry.Entity.CreatedAt == default)
                    {
                        entry.Entity.CreatedAt = now;
                    }

                    entry.Entity.CreatedBy ??= actorId;
                }
                else if (entry.State == EntityState.Modified)
                {
                    entry.Entity.LastModifiedAt = now;
                    entry.Entity.LastModifiedBy = actorId;
                    entry.Entity.UpdatedAt = now;
                    entry.Entity.UpdatedBy = actorId;
                }
            }
        }
    }
}
