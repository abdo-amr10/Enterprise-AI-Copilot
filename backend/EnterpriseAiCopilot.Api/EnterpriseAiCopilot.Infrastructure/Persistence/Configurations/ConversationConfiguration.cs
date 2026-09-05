using EnterpriseAiCopilot.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace EnterpriseAiCopilot.Infrastructure.Persistence.Configurations;

public class ConversationConfiguration : IEntityTypeConfiguration<Conversation>
{
    public void Configure(EntityTypeBuilder<Conversation> builder)
    {
        builder.ToTable("Conversations");
        builder.HasKey(c => c.Id);
        builder.Property(c => c.UserId).IsRequired().HasMaxLength(450);
        builder.Property(c => c.BranchId).IsRequired().HasMaxLength(50);
        builder.Property(c => c.Title).HasMaxLength(200);
        builder.Property(c => c.SemanticLayerId).IsRequired();
        builder.HasIndex(c => new { c.UserId, c.BranchId, c.UpdatedAt });
        builder.HasOne(c => c.SemanticLayer).WithMany().HasForeignKey(c => c.SemanticLayerId).OnDelete(DeleteBehavior.Restrict);
    }
}
