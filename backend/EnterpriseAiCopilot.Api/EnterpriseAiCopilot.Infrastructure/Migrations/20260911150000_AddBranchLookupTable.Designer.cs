using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using EnterpriseAiCopilot.Infrastructure.Persistence;

#nullable disable

namespace EnterpriseAiCopilot.Infrastructure.Migrations;

[DbContext(typeof(ApplicationDbContext))]
partial class AddBranchLookupTable
{
    protected override void BuildTargetModel(ModelBuilder modelBuilder)
    {
        // The current model is maintained by ApplicationDbContextModelSnapshot.cs.
    }
}
