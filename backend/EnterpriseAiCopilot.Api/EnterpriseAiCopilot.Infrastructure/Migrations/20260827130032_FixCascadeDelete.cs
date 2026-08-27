using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace EnterpriseAiCopilot.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class FixCascadeDelete : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateIndex(
                name: "IX_AllowedTables_SemanticLayerId",
                table: "AllowedTables",
                column: "SemanticLayerId");

            migrationBuilder.AddForeignKey(
                name: "FK_AllowedTables_SemanticLayers_SemanticLayerId",
                table: "AllowedTables",
                column: "SemanticLayerId",
                principalTable: "SemanticLayers",
                principalColumn: "Id",
                onDelete: ReferentialAction.Cascade);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_AllowedTables_SemanticLayers_SemanticLayerId",
                table: "AllowedTables");

            migrationBuilder.DropIndex(
                name: "IX_AllowedTables_SemanticLayerId",
                table: "AllowedTables");
        }
    }
}
