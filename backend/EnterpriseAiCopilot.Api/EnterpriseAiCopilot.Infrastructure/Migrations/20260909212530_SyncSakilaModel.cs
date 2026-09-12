using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace EnterpriseAiCopilot.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class SyncSakilaModel : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql("""
                IF EXISTS (
                    SELECT 1
                    FROM sys.columns c
                    INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
                    WHERE c.object_id = OBJECT_ID(N'[dbo].[Users]')
                      AND c.name = N'BranchId'
                      AND (t.name <> N'nvarchar' OR c.max_length <> 20)
                )
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM sys.indexes
                        WHERE name = N'IX_Users_BranchId'
                          AND object_id = OBJECT_ID(N'[dbo].[Users]')
                    )
                        DROP INDEX [IX_Users_BranchId] ON [dbo].[Users];

                    ALTER TABLE [dbo].[Users]
                    ALTER COLUMN [BranchId] nvarchar(20) NULL;
                END;
                """);

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

            migrationBuilder.Sql("""
                IF NOT EXISTS (
                    SELECT 1 FROM sys.indexes
                    WHERE name = N'IX_Users_BranchId'
                      AND object_id = OBJECT_ID(N'[dbo].[Users]')
                )
                    CREATE INDEX [IX_Users_BranchId] ON [dbo].[Users] ([BranchId]);
                """);

            migrationBuilder.Sql("""
                INSERT INTO [dbo].[branches] ([branch_id], [branch_name])
                SELECT DISTINCT u.[BranchId], u.[BranchId]
                FROM [dbo].[Users] u
                LEFT JOIN [dbo].[branches] b ON b.[branch_id] = u.[BranchId]
                WHERE u.[BranchId] IS NOT NULL
                  AND b.[branch_id] IS NULL;
                """);

            migrationBuilder.Sql("""
                IF OBJECT_ID(N'[dbo].[branches]', N'U') IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM sys.foreign_keys
                       WHERE name = N'FK_Users_branches_BranchId'
                         AND parent_object_id = OBJECT_ID(N'[dbo].[Users]')
                   )
                BEGIN
                    ALTER TABLE [dbo].[Users]
                    ADD CONSTRAINT [FK_Users_branches_BranchId]
                    FOREIGN KEY ([BranchId]) REFERENCES [dbo].[branches] ([branch_id]);
                END;
                """);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql("""
                IF EXISTS (
                    SELECT 1 FROM sys.foreign_keys
                    WHERE name = N'FK_Users_branches_BranchId'
                      AND parent_object_id = OBJECT_ID(N'[dbo].[Users]')
                )
                    ALTER TABLE [dbo].[Users] DROP CONSTRAINT [FK_Users_branches_BranchId];
                """);

            migrationBuilder.Sql("""
                IF OBJECT_ID(N'[dbo].[branches]', N'U') IS NOT NULL
                    DROP TABLE [dbo].[branches];
                """);

            migrationBuilder.Sql("""
                IF EXISTS (
                    SELECT 1 FROM sys.indexes
                    WHERE name = N'IX_Users_BranchId'
                      AND object_id = OBJECT_ID(N'[dbo].[Users]')
                )
                    DROP INDEX [IX_Users_BranchId] ON [dbo].[Users];
                """);

            migrationBuilder.AlterColumn<string>(
                name: "BranchId",
                table: "Users",
                type: "nvarchar(max)",
                nullable: true,
                oldClrType: typeof(string),
                oldType: "nvarchar(20)",
                oldNullable: true);
        }
    }
}
