using EnterpriseAiCopilot.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace EnterpriseAiCopilot.Infrastructure.Persistence.Configurations
{
    public class AuditLogConfiguration : IEntityTypeConfiguration<AuditLog>
    {
        public void Configure(EntityTypeBuilder<AuditLog> builder)
        {
            builder.HasKey(a => a.Id);

            builder.Property(a => a.EventId)
                .IsRequired()
                .HasMaxLength(50);

            builder.Property(a => a.Action)
                .IsRequired()
                .HasMaxLength(100);

            builder.Property(a => a.UserId)
                .IsRequired()
                .HasMaxLength(100);

            builder.Property(a => a.Status)
                .IsRequired()
                .HasMaxLength(50);

            builder.HasIndex(a => a.Timestamp);
            builder.HasIndex(a => a.UserId);
            builder.HasIndex(a => a.Action);
        }
    }
}