using EnterpriseAiCopilot.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace EnterpriseAiCopilot.Infrastructure.Persistence.Configurations;

public class UserTablePermissionConfiguration : IEntityTypeConfiguration<UserTablePermission>
{
    public void Configure(EntityTypeBuilder<UserTablePermission> builder)
    {
        builder.HasKey(permission => permission.Id);

        builder.Property(permission => permission.TableName)
            .IsRequired()
            .HasMaxLength(256);

        builder.HasIndex(permission => new
        {
            permission.UserId,
            permission.SemanticLayerId,
            permission.TableName
        }).IsUnique();

        builder.HasOne(permission => permission.User)
            .WithMany()
            .HasForeignKey(permission => permission.UserId)
            .OnDelete(DeleteBehavior.Cascade);

        builder.HasOne(permission => permission.SemanticLayer)
            .WithMany()
            .HasForeignKey(permission => permission.SemanticLayerId)
            .OnDelete(DeleteBehavior.Cascade);
    }
}
