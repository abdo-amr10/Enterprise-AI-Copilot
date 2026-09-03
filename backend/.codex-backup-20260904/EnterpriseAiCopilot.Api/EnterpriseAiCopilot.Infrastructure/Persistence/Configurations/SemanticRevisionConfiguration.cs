using EnterpriseAiCopilot.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Infrastructure.Persistence.Configurations
{
    public class SemanticRevisionConfiguration : IEntityTypeConfiguration<SemanticRevision>
    {
        public void Configure(EntityTypeBuilder<SemanticRevision> builder)
        {
            builder.HasKey(r => r.Id);

            builder.Property(r => r.ContentJson)
                .IsRequired(); 

            builder.Property(r => r.Status)
                .IsRequired()
                .HasMaxLength(20); 

            builder.Property(r => r.ReviewedBy)
                .HasMaxLength(100);

            builder.Property(r => r.ReviewNotes)
                .HasMaxLength(1000);
        }
    }
}
