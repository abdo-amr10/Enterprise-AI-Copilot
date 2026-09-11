using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace EnterpriseAiCopilot.Infrastructure.Migrations;

[Migration("20260906120000_AddConversations")]
public partial class AddConversations : Migration
{
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.CreateTable(
            name: "Conversations",
            columns: table => new
            {
                Id = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                UserId = table.Column<string>(type: "nvarchar(450)", maxLength: 450, nullable: false),
                BranchId = table.Column<string>(type: "nvarchar(50)", maxLength: 50, nullable: false),
                SemanticLayerId = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                Title = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                IsArchived = table.Column<bool>(type: "bit", nullable: false),
                CreatedAt = table.Column<DateTime>(type: "datetime2", nullable: false),
                CreatedBy = table.Column<string>(type: "nvarchar(max)", nullable: true),
                LastModifiedAt = table.Column<DateTime>(type: "datetime2", nullable: true),
                LastModifiedBy = table.Column<string>(type: "nvarchar(max)", nullable: true),
                UpdatedAt = table.Column<DateTime>(type: "datetime2", nullable: true),
                UpdatedBy = table.Column<string>(type: "nvarchar(max)", nullable: true)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_Conversations", x => x.Id);
                table.ForeignKey("FK_Conversations_SemanticLayers_SemanticLayerId", x => x.SemanticLayerId, "SemanticLayers", "Id", onDelete: ReferentialAction.Restrict);
            });

        migrationBuilder.AddColumn<Guid>(
            name: "ConversationId",
            table: "CopilotQueryHistories",
            type: "uniqueidentifier",
            nullable: true);

        migrationBuilder.CreateIndex("IX_Conversations_SemanticLayerId", "Conversations", "SemanticLayerId");
        migrationBuilder.CreateIndex("IX_Conversations_UserId_BranchId_UpdatedAt", "Conversations", new[] { "UserId", "BranchId", "UpdatedAt" });
        migrationBuilder.CreateIndex("IX_CopilotQueryHistories_ConversationId", "CopilotQueryHistories", "ConversationId");
        migrationBuilder.AddForeignKey(
            name: "FK_CopilotQueryHistories_Conversations_ConversationId",
            table: "CopilotQueryHistories",
            column: "ConversationId",
            principalTable: "Conversations",
            principalColumn: "Id",
            onDelete: ReferentialAction.SetNull);
    }

    protected override void Down(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.DropForeignKey(
            name: "FK_CopilotQueryHistories_Conversations_ConversationId",
            table: "CopilotQueryHistories");
        migrationBuilder.DropIndex("IX_CopilotQueryHistories_ConversationId", "CopilotQueryHistories");
        migrationBuilder.DropColumn("ConversationId", "CopilotQueryHistories");
        migrationBuilder.DropTable("Conversations");
    }
}
