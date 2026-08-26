using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace EnterpriseAiCopilot.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class AddUniqueActiveLayerConstraint : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql("UPDATE SemanticLayers SET IsActive = 0 WHERE IsActive = 1");

            migrationBuilder.CreateIndex(
                name: "IX_SemanticLayers_IsActive",
                table: "SemanticLayers",
                column: "IsActive",
                unique: true,
                filter: "[IsActive] = 1");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_SemanticLayers_IsActive",
                table: "SemanticLayers");
        }
    }
}
