using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace EnterpriseAiCopilot.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class PersistQueryResultsAndSchemaSnapshot : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "PhysicalSchemaJson",
                table: "SemanticRevisions",
                type: "nvarchar(max)",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "ResultJson",
                table: "CopilotQueryHistories",
                type: "nvarchar(max)",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "PhysicalSchemaJson",
                table: "SemanticRevisions");

            migrationBuilder.DropColumn(
                name: "ResultJson",
                table: "CopilotQueryHistories");
        }
    }
}
