using EnterpriseAiCopilot.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Infrastructure.Persistence.Configurations
{
    public class SemanticSourceFileConfiguration : IEntityTypeConfiguration<SemanticSourceFile>
    {
        public void Configure(EntityTypeBuilder<SemanticSourceFile> builder)
        {
            builder.HasKey(f => f.Id);

            builder.Property(f => f.FileName)
                .IsRequired()
                .HasMaxLength(255);

            builder.Property(f => f.FileType)
                .IsRequired()
                .HasMaxLength(50); 

            builder.Property(f => f.StoragePath)
                .IsRequired()
                .HasMaxLength(1000); 

            builder.Property(f => f.UploadedBy)
                .IsRequired()
                .HasMaxLength(100);
        }
    }
}
