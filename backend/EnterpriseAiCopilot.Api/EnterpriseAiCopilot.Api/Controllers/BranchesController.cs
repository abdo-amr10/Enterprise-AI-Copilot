using EnterpriseAiCopilot.Application.Common.Interfaces;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace EnterpriseAiCopilot.Api.Controllers;

[ApiController]
[Route("api/v1/branches")]
[Authorize(Roles = "admin")]
public sealed class BranchesController : ControllerBase
{
    private readonly IApplicationDbContext _context;

    public BranchesController(IApplicationDbContext context)
    {
        _context = context;
    }

    [HttpGet]
    public async Task<IActionResult> GetBranches(CancellationToken cancellationToken)
    {
        var branches = await _context.Branches
            .AsNoTracking()
            .OrderBy(branch => branch.BranchId)
            .Select(branch => new
            {
                Id = branch.BranchId,
                Name = string.IsNullOrWhiteSpace(branch.BranchName)
                    ? branch.BranchId
                    : branch.BranchName
            })
            .ToListAsync(cancellationToken);

        return Ok(branches);
    }
}
