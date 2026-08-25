using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Infrastructure.Persistence
{
    public class ApplicationDbContext : DbContext, IApplicationDbContext
    {
        public ApplicationDbContext(DbContextOptions<ApplicationDbContext> options) : base(options)
        {
        }

        public DbSet<User> Users => Set<User>();
        public DbSet<SemanticLayer> SemanticLayers => Set<SemanticLayer>();
        public DbSet<SemanticSourceFile> SemanticSourceFiles => Set<SemanticSourceFile>();
        public DbSet<SemanticRevision> SemanticRevisions => Set<SemanticRevision>();
        public DbSet<CopilotQueryHistory> CopilotQueryHistories => Set<CopilotQueryHistory>();
        public DbSet<AllowedTable> AllowedTables => Set<AllowedTable>();
        public DbSet<AuditLog> AuditLogs => Set<AuditLog>();
        protected override void OnModelCreating(ModelBuilder modelBuilder)
        {
            modelBuilder.ApplyConfigurationsFromAssembly(typeof(ApplicationDbContext).Assembly);
            base.OnModelCreating(modelBuilder);
        }
    }
}
