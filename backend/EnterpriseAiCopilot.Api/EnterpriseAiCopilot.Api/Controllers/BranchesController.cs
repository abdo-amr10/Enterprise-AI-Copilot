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
    public async Task<IActionResult> GetBranches(
        [FromQuery] Guid? semanticLayerId,
        CancellationToken cancellationToken)
    {
        var layerQuery = _context.SemanticLayers
            .AsNoTracking()
            .AsQueryable();

        var policyJson = await (semanticLayerId.HasValue
                ? layerQuery.Where(layer => layer.Id == semanticLayerId.Value)
                : layerQuery.Where(layer => layer.IsActive))
            .Select(layer => layer.RlsPolicyJson)
            .FirstOrDefaultAsync(cancellationToken);

        if (string.IsNullOrWhiteSpace(policyJson))
            return BadRequest(new { message = "RLS policy with branchMapping must be uploaded for the selected semantic layer first." });

        BranchMapping? mapping;
        try
        {
            using var document = JsonDocument.Parse(policyJson);
            var branchMapping = document.RootElement
                .EnumerateObject()
                .FirstOrDefault(property =>
                    string.Equals(property.Name, "branchMapping", StringComparison.OrdinalIgnoreCase));

            if (branchMapping.Value.ValueKind != JsonValueKind.Undefined)
            {
                mapping = JsonSerializer.Deserialize<BranchMapping>(branchMapping.Value.GetRawText(),
                    new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
            }
            else
                mapping = null;
        }
        catch (JsonException)
        {
            return BadRequest(new { message = "Stored RLS policy is invalid JSON." });
        }

        if (mapping == null || !IsSafeIdentifier(mapping.Table) || !IsSafeIdentifier(mapping.IdColumn) ||
            (!string.IsNullOrWhiteSpace(mapping.NameColumn) && !IsSafeIdentifier(mapping.NameColumn)))
            return BadRequest(new { message = "The selected layer RLS policy must contain valid branchMapping table and column names." });

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
