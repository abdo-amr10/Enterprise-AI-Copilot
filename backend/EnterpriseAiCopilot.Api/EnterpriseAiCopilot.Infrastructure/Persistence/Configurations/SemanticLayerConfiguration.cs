using EnterpriseAiCopilot.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Infrastructure.Persistence.Configurations
{
    public class SemanticLayerConfiguration : IEntityTypeConfiguration<SemanticLayer>
    {
        public void Configure(EntityTypeBuilder<SemanticLayer> builder)
        {
            builder.HasKey(s => s.Id);

            builder.Property(s => s.Name)
                .IsRequired()
                .HasMaxLength(100);

            builder.Property(s => s.DatabaseName)
                .IsRequired()
                .HasMaxLength(100);

            builder.Property(s => s.Description)
                .HasMaxLength(500);

            builder.HasMany(s => s.SourceFiles)
                .WithOne(f => f.SemanticLayer)
                .HasForeignKey(f => f.SemanticLayerId)
                .OnDelete(DeleteBehavior.Cascade);

            builder.HasMany(s => s.Revisions)
                .WithOne(r => r.SemanticLayer)
                .HasForeignKey(r => r.SemanticLayerId)
                .OnDelete(DeleteBehavior.Cascade);
        }
    }
}
