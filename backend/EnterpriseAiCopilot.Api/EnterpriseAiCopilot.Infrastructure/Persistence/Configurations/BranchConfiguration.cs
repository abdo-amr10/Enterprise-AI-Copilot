using EnterpriseAiCopilot.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace EnterpriseAiCopilot.Infrastructure.Persistence.Configurations;

public sealed class BranchConfiguration : IEntityTypeConfiguration<Branch>
{
    public void Configure(EntityTypeBuilder<Branch> builder)
    {
        builder.ToTable("branches");
        builder.HasKey(branch => branch.BranchId);
        builder.Property(branch => branch.BranchId).HasColumnName("branch_id").HasMaxLength(20);
        builder.Property(branch => branch.BranchName).HasColumnName("branch_name").HasMaxLength(100);
    }
}
