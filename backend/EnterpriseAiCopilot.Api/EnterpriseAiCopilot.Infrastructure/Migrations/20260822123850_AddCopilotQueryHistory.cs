using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace EnterpriseAiCopilot.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class AddCopilotQueryHistory : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<int>(
                name: "RegeneratedObjectsCount",
                table: "SemanticRevisions",
                type: "int",
                nullable: false,
                defaultValue: 0);

            migrationBuilder.AddColumn<string>(
                name: "RegenerationType",
                table: "SemanticRevisions",
                type: "nvarchar(max)",
                nullable: false,
                defaultValue: "");

            migrationBuilder.CreateTable(
                name: "CopilotQueryHistories",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    UserId = table.Column<string>(type: "nvarchar(450)", maxLength: 450, nullable: false),
                    UserPrompt = table.Column<string>(type: "nvarchar(1500)", maxLength: 1500, nullable: false),
                    GeneratedSql = table.Column<string>(type: "nvarchar(max)", nullable: true),
                    SemanticLayerId = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    Status = table.Column<string>(type: "nvarchar(50)", maxLength: 50, nullable: false),
                    ErrorMessage = table.Column<string>(type: "nvarchar(2000)", maxLength: 2000, nullable: true),
                    ExecutionTimeMs = table.Column<long>(type: "bigint", nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "datetime2", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CopilotQueryHistories", x => x.Id);
                    table.ForeignKey(
                        name: "FK_CopilotQueryHistories_SemanticLayers_SemanticLayerId",
                        column: x => x.SemanticLayerId,
                        principalTable: "SemanticLayers",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateIndex(
                name: "IX_CopilotQueryHistories_SemanticLayerId",
                table: "CopilotQueryHistories",
                column: "SemanticLayerId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "CopilotQueryHistories");

            migrationBuilder.DropColumn(
                name: "RegeneratedObjectsCount",
                table: "SemanticRevisions");

            migrationBuilder.DropColumn(
                name: "RegenerationType",
                table: "SemanticRevisions");
        }
    }
}
