using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace EnterpriseAiCopilot.Infrastructure.Migrations;

[Migration("20260911150000_AddBranchLookupTable")]
public partial class AddBranchLookupTable : Migration
{
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.Sql("""
            IF OBJECT_ID(N'[dbo].[branches]', N'U') IS NULL
            BEGIN
                CREATE TABLE [dbo].[branches]
                (
                    [branch_id] nvarchar(20) NOT NULL,
                    [branch_name] nvarchar(100) NOT NULL,
                    CONSTRAINT [PK_branches] PRIMARY KEY ([branch_id])
                );
            END;
            """);
    }

    protected override void Down(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.Sql("""
            IF OBJECT_ID(N'[dbo].[branches]', N'U') IS NOT NULL
                DROP TABLE [dbo].[branches];
            """);
    }
}
