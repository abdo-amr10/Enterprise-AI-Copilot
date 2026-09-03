using EnterpriseAiCopilot.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Infrastructure.Persistence.Configurations
{
    public class QueryHistoryConfiguration : IEntityTypeConfiguration<CopilotQueryHistory>
    {
        public void Configure(EntityTypeBuilder<CopilotQueryHistory> builder)
        {
            builder.ToTable("CopilotQueryHistories");

            builder.HasKey(q => q.Id);

            builder.Property(q => q.UserId)
                .IsRequired()
                .HasMaxLength(450); 

            builder.Property(q => q.UserPrompt)
                .IsRequired()
                .HasMaxLength(1500); 

            builder.Property(q => q.BranchId)
                .IsRequired()
                .HasMaxLength(50);

            builder.Property(q => q.GeneratedSql)
                .HasColumnType("nvarchar(max)");

            builder.Property(q => q.Status)
                .IsRequired()
                .HasMaxLength(50); 

            builder.Property(q => q.ErrorMessage)
                .HasMaxLength(2000);

            builder.HasOne(q => q.SemanticLayer)
                .WithMany()
                .HasForeignKey(q => q.SemanticLayerId)
                .OnDelete(DeleteBehavior.Restrict); 
        }
    }
}
