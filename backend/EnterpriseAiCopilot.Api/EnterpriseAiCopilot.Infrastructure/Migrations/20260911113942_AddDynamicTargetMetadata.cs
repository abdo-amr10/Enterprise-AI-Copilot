using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace EnterpriseAiCopilot.Infrastructure.Migrations;

public partial class AddDynamicTargetMetadata : Migration
{
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.Sql("""
            IF COL_LENGTH(N'dbo.SemanticLayers', N'DatabaseMetadataJson') IS NULL
                ALTER TABLE [dbo].[SemanticLayers] ADD [DatabaseMetadataJson] nvarchar(max) NULL;
            """);

        migrationBuilder.Sql("""
            IF COL_LENGTH(N'dbo.SemanticLayers', N'RlsPolicyJson') IS NULL
                ALTER TABLE [dbo].[SemanticLayers] ADD [RlsPolicyJson] nvarchar(max) NULL;
            """);
    }

    protected override void Down(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.Sql("""
            IF COL_LENGTH(N'dbo.SemanticLayers', N'DatabaseMetadataJson') IS NOT NULL
                ALTER TABLE [dbo].[SemanticLayers] DROP COLUMN [DatabaseMetadataJson];
            """);

        migrationBuilder.Sql("""
            IF COL_LENGTH(N'dbo.SemanticLayers', N'RlsPolicyJson') IS NOT NULL
                ALTER TABLE [dbo].[SemanticLayers] DROP COLUMN [RlsPolicyJson];
            """);
    }
}
