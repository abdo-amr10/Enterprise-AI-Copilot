using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.DTOs.Admin;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace EnterpriseAiCopilot.Api.Controllers;

[ApiController]
[Route("api/v1/dashboard")]
[Authorize(Roles = "admin")]
public sealed class AdminDashboardController : ControllerBase
{
    private readonly IApplicationDbContext _context;

    public AdminDashboardController(IApplicationDbContext context)
    {
        _context = context;
    }

    [HttpGet("metrics")]
    public async Task<IActionResult> GetMetrics(CancellationToken cancellationToken)
    {
        var nowUtc = DateTime.UtcNow;
        var startOfDayUtc = nowUtc.Date;
        var endOfDayUtc = startOfDayUtc.AddDays(1);

        var todayQueries = _context.CopilotQueryHistories
            .AsNoTracking()
            .Where(query => query.CreatedAt >= startOfDayUtc &&
                            query.CreatedAt < endOfDayUtc &&
                            query.Status == "Completed");

        var response = new AdminDashboardMetricsResponse
        {
            ActiveUsers = await todayQueries
                .Select(query => query.UserId)
                .Distinct()
                .CountAsync(cancellationToken),
            QuestionsToday = await todayQueries.CountAsync(cancellationToken),
            TotalUsers = await _context.Users
                .AsNoTracking()
                .CountAsync(cancellationToken),
            AsOfUtc = nowUtc
        };

        return Ok(response);
    }
}
