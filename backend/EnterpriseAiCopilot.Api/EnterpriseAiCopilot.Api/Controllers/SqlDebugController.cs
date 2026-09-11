using System.Diagnostics;
using System.Security.Claims;
using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.DTOs.Copilot;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace EnterpriseAiCopilot.Api.Controllers;

[ApiController]
[Authorize(Roles = "admin")]
[Route("api/v1/copilot/debug")]
public class SqlDebugController : ControllerBase
{
    private readonly IDynamicSqlExecutor _executor;

    public SqlDebugController(IDynamicSqlExecutor executor) => _executor = executor;

    [HttpPost("run")]
    public async Task<IActionResult> Run([FromBody] SqlDebugRequest request, CancellationToken cancellationToken)
    {
        if (!Guid.TryParse(request.SemanticLayerId, out var layerId) || string.IsNullOrWhiteSpace(request.Sql))
            return BadRequest(new { status = "Failed", errorCode = "BAD_REQUEST", message = "SemanticLayerId and Sql are required." });

        if (!Guid.TryParse(User.FindFirstValue(ClaimTypes.NameIdentifier), out var userId))
            return Unauthorized(new { status = "Failed", errorCode = "UNAUTHORIZED", message = "User ID claim is missing." });

        var branchId = User.FindFirstValue("store_id") ?? User.FindFirstValue("storeId") ?? User.FindFirstValue("branchId");
        if (string.IsNullOrWhiteSpace(branchId))
            return BadRequest(new { status = "Failed", errorCode = "BAD_REQUEST", message = "Branch ID claim is missing." });

        var total = Stopwatch.StartNew();
        var response = new SqlDebugResponse { SemanticLayerId = layerId.ToString(), Sql = request.Sql };

        var validationWatch = Stopwatch.StartNew();
        var validation = await _executor.ValidateQueryAsync(request.Sql, layerId, userId, cancellationToken);
        validationWatch.Stop();
        response.Stages.Add(new SqlDebugStage
        {
            Name = "Validation & RLS",
            Status = validation.IsSuccess ? "Passed" : "Failed",
            DurationMs = validationWatch.ElapsedMilliseconds,
            Message = validation.IsSuccess ? "SQL syntax, allowed tables, and store_id RLS passed." : validation.ErrorMessage,
            Data = validation.Data
        });

        if (!validation.IsSuccess)
        {
            total.Stop();
            response.TotalTimeMs = total.ElapsedMilliseconds;
            response.Stages.Add(new SqlDebugStage { Name = "Execute", Status = "Skipped", Message = "Execution was skipped because validation failed." });
            return Ok(response);
        }

        var executeWatch = Stopwatch.StartNew();
        var execution = await _executor.ExecuteQueryAsync(request.Sql, branchId, layerId, userId, cancellationToken);
        executeWatch.Stop();
        response.Stages.Add(new SqlDebugStage
        {
            Name = "Execute",
            Status = execution.IsSuccess ? "Passed" : "Failed",
            DurationMs = executeWatch.ElapsedMilliseconds,
            Message = execution.IsSuccess ? "Query executed successfully." : execution.ErrorMessage,
            Data = execution.Data
        });

        total.Stop();
        response.TotalTimeMs = total.ElapsedMilliseconds;
        return Ok(response);
    }
}
