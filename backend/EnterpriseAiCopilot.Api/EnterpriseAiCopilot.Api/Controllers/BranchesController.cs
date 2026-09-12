using EnterpriseAiCopilot.Application.Common.Interfaces;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.Data.SqlClient;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace EnterpriseAiCopilot.Api.Controllers;

[ApiController]
[Route("api/v1/branches")]
[Authorize(Roles = "admin")]
public sealed class BranchesController : ControllerBase
{
    private readonly IApplicationDbContext _context;
    private readonly IConfiguration _configuration;

    public BranchesController(IApplicationDbContext context, IConfiguration configuration)
    {
        _context = context;
        _configuration = configuration;
    }

    [HttpGet]
    public async Task<IActionResult> GetBranches(CancellationToken cancellationToken)
    {
        var policyJson = await _context.SemanticLayers
            .AsNoTracking()
            .Where(layer => layer.IsActive)
            .Select(layer => layer.RlsPolicyJson)
            .FirstOrDefaultAsync(cancellationToken);

        if (string.IsNullOrWhiteSpace(policyJson))
            return BadRequest(new { message = "RLS policy with branchMapping must be uploaded first." });

        BranchMapping? mapping;
        try
        {
            using var document = JsonDocument.Parse(policyJson);
            if (!document.RootElement.TryGetProperty("branchMapping", out var branchMapping))
                return BadRequest(new { message = "RLS policy must contain branchMapping." });
            mapping = JsonSerializer.Deserialize<BranchMapping>(branchMapping.GetRawText(),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
        }
        catch (JsonException)
        {
            return BadRequest(new { message = "Stored RLS policy is invalid JSON." });
        }

        if (mapping == null || !IsSafeIdentifier(mapping.Table) || !IsSafeIdentifier(mapping.IdColumn) ||
            (!string.IsNullOrWhiteSpace(mapping.NameColumn) && !IsSafeIdentifier(mapping.NameColumn)))
            return BadRequest(new { message = "branchMapping contains invalid table or column names." });

        var connectionString = _configuration.GetConnectionString("TargetConnection");
        if (string.IsNullOrWhiteSpace(connectionString))
            return BadRequest(new { message = "TargetConnection is not configured." });

        var nameExpression = string.IsNullOrWhiteSpace(mapping.NameColumn)
            ? $"CONVERT(nvarchar(4000), [{mapping.IdColumn}])"
            : $"COALESCE(CONVERT(nvarchar(4000), [{mapping.NameColumn}]), CONVERT(nvarchar(4000), [{mapping.IdColumn}]))";
        var sql = $"SELECT DISTINCT CONVERT(nvarchar(4000), [{mapping.IdColumn}]) AS [Id], {nameExpression} AS [Name] FROM [{mapping.Table}] ORDER BY [Id]";

        var branches = new List<object>();
        await using var connection = new SqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new SqlCommand(sql, connection);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            branches.Add(new
            {
                Id = reader["Id"]?.ToString() ?? string.Empty,
                Name = reader["Name"]?.ToString() ?? reader["Id"]?.ToString() ?? string.Empty
            });
        }

        return Ok(branches);
    }

    private static bool IsSafeIdentifier(string? value) =>
        !string.IsNullOrWhiteSpace(value) && Regex.IsMatch(value, "^[A-Za-z_][A-Za-z0-9_]*$");

    private sealed class BranchMapping
    {
        public string Table { get; set; } = string.Empty;
        public string IdColumn { get; set; } = string.Empty;
        public string? NameColumn { get; set; }
    }
}
