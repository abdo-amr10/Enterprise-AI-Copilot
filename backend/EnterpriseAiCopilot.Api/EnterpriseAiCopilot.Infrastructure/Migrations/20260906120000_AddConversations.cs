using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace EnterpriseAiCopilot.Infrastructure.Migrations;

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

        migrationBuilder.CreateIndex(
            name: "IX_Conversations_SemanticLayerId",
            table: "Conversations",
            column: "SemanticLayerId");

        migrationBuilder.CreateIndex(
            name: "IX_Conversations_UserId_BranchId_UpdatedAt",
            table: "Conversations",
            columns: new[] { "UserId", "BranchId", "UpdatedAt" });

        migrationBuilder.CreateIndex(
            name: "IX_CopilotQueryHistories_ConversationId",
            table: "CopilotQueryHistories",
            column: "ConversationId");

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
        migrationBuilder.DropForeignKey("FK_CopilotQueryHistories_Conversations_ConversationId", "CopilotQueryHistories");
        migrationBuilder.DropTable("Conversations");
        migrationBuilder.DropIndex("IX_CopilotQueryHistories_ConversationId", "CopilotQueryHistories");
        migrationBuilder.DropColumn("ConversationId", "CopilotQueryHistories");
    }
}
