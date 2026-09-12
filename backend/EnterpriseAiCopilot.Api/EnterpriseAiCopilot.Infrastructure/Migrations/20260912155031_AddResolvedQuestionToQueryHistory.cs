using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace EnterpriseAiCopilot.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class AddResolvedQuestionToQueryHistory : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "ResolvedQuestion",
                table: "CopilotQueryHistories",
                type: "nvarchar(4000)",
                maxLength: 4000,
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "ResolvedQuestion",
                table: "CopilotQueryHistories");
        }
    }
}
