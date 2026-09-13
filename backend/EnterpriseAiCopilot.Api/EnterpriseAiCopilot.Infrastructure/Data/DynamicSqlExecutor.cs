using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.DependencyInjection;
using Dapper;
using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.Common.Models;
using Microsoft.EntityFrameworkCore;
using Microsoft.SqlServer.TransactSql.ScriptDom;
using System.Text.Json;

namespace EnterpriseAiCopilot.Infrastructure.Data
{
    public class DynamicSqlExecutor : IDynamicSqlExecutor
    {
        private readonly IConfiguration _configuration;
        private readonly ILogger<DynamicSqlExecutor> _logger;
        private readonly IMemoryCache _cache;
        private readonly IServiceScopeFactory _scopeFactory;

        private readonly string[] _forbiddenKeywords =
        {
            "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
            "TRUNCATE", "EXEC", "EXECUTE", "CREATE", "GRANT",
            "REVOKE", "XP_", "SP_", "MERGE", "CALL"
        };

        public DynamicSqlExecutor(
            IConfiguration configuration,
            ILogger<DynamicSqlExecutor> logger,
            IMemoryCache cache,
            IServiceScopeFactory scopeFactory)
        {
            _configuration = configuration;
            _logger = logger;
            _cache = cache;
            _scopeFactory = scopeFactory;
        }

        private static string AllowedTablesCacheKey(Guid layerId) => $"AllowedTables_{layerId}";

        private async Task<HashSet<string>> GetAllowedTablesAsync(
            Guid layerId,
            Guid userId,
            CancellationToken cancellationToken)
        {
            var cacheKey = AllowedTablesCacheKey(layerId);

            var cachedAllowedTables = await _cache.GetOrCreateAsync(cacheKey, async entry =>
            {
                entry.AbsoluteExpirationRelativeToNow = TimeSpan.FromHours(24);

                using var scope = _scopeFactory.CreateScope();
                var dbContext = scope.ServiceProvider.GetRequiredService<IApplicationDbContext>();

                var tables = await dbContext.AllowedTables
                    .Where(t => t.IsAllowed && t.SemanticLayerId == layerId)
                    .Select(t => t.TableName)
                    .ToListAsync(cancellationToken);

                return tables.ToHashSet(StringComparer.OrdinalIgnoreCase);
            }) ?? new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var allowedTables = new HashSet<string>(cachedAllowedTables, StringComparer.OrdinalIgnoreCase);

            using var scope = _scopeFactory.CreateScope();
            var dbContext = scope.ServiceProvider.GetRequiredService<IApplicationDbContext>();
            var userPermissions = await dbContext.UserTablePermissions
                .Where(permission => permission.UserId == userId && permission.SemanticLayerId == layerId)
                .Select(permission => new { permission.TableName, permission.IsAllowed })
                .ToListAsync(cancellationToken);

            foreach (var permission in userPermissions)
            {
                if (!permission.IsAllowed)
                    allowedTables.Remove(permission.TableName);
            }

            return allowedTables;
        }

        public async Task<Result<object>> ExecuteQueryAsync(
            string sqlQuery,
            string branchId,
            Guid semanticLayerId,
            Guid userId,
            CancellationToken cancellationToken = default)
        {
            if (string.IsNullOrWhiteSpace(sqlQuery))
            {
                return Result<object>.Failure("SQL query cannot be empty.");
            }

            var validationResult = await ValidateQueryAsync(sqlQuery, semanticLayerId, userId, cancellationToken);
            if (!validationResult.IsSuccess)
                return validationResult;

            try
            {
                // The system database (SystemConnection) stores users, permissions,
                // conversations and audit data. Business SQL must run against the
                // separately configured target database.
                var connectionString = _configuration.GetConnectionString("TargetConnection");

                if (string.IsNullOrWhiteSpace(connectionString))
                {
                    return Result<object>.Failure("DATABASE_CONFIGURATION_ERROR: TargetConnection is missing.");
                }

                await using var connection = new SqlConnection(connectionString);
                await connection.OpenAsync(cancellationToken);

                // Keep the historical aliases for existing semantic layers, and
                // expose the same authenticated scope under the parameter name
                // declared by the active semantic-layer RLS policy.
                var parameters = new DynamicParameters();
                parameters.Add("UserStoreId", branchId);
                parameters.Add("UserBranchId", branchId);

                var policyParameter = await GetConfiguredScopeParameterAsync(semanticLayerId, cancellationToken);
                if (!string.IsNullOrWhiteSpace(policyParameter))
                    parameters.Add(policyParameter.TrimStart('@'), branchId);

                var command = new CommandDefinition(
                    sqlQuery,
                    parameters,
                    commandTimeout: 30,
                    cancellationToken: cancellationToken
                );

                var result = await connection.QueryAsync(command);
                var rows = result
                    .Select(row => (IDictionary<string, object>)row)
                    .Select(row => new Dictionary<string, object>(row, StringComparer.OrdinalIgnoreCase))
                    .ToList();

                return Result<object>.Success(rows);
            }
            catch (OperationCanceledException) { throw; }
            catch (SqlException ex)
            {
                _logger.LogError(ex, "Database execution error during dynamic SQL execution.");
                return Result<object>.Failure($"DATABASE_EXECUTION_ERROR: {ex.Message}");
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Unexpected error during dynamic SQL execution.");
                return Result<object>.Failure("UNEXPECTED_ERROR: Failed to process query execution.");
            }
        }

        private async Task<string?> GetConfiguredScopeParameterAsync(
            Guid semanticLayerId,
            CancellationToken cancellationToken)
        {
            using var scope = _scopeFactory.CreateScope();
            var dbContext = scope.ServiceProvider.GetRequiredService<IApplicationDbContext>();

            var explicitPolicyJson = await dbContext.SemanticLayers
                .AsNoTracking()
                .Where(layer => layer.Id == semanticLayerId)
                .Select(layer => layer.RlsPolicyJson)
                .FirstOrDefaultAsync(cancellationToken);

            if (!string.IsNullOrWhiteSpace(explicitPolicyJson))
            {
                try
                {
                    using var explicitDocument = JsonDocument.Parse(explicitPolicyJson);
                    if (explicitDocument.RootElement.TryGetProperty("scopeParameter", out var parameter))
                        return parameter.GetString();
                }
                catch (JsonException)
                {
                    return null;
                }
            }

            var contentJson = await dbContext.SemanticRevisions
                .AsNoTracking()
                .Where(revision => revision.SemanticLayerId == semanticLayerId &&
                    (revision.Status == "Approved" || revision.Status == "Active"))
                .OrderByDescending(revision => revision.VersionNumber)
                .Select(revision => revision.ContentJson)
                .FirstOrDefaultAsync(cancellationToken);

            if (string.IsNullOrWhiteSpace(contentJson))
                return null;

            try
            {
                using var document = JsonDocument.Parse(contentJson);
                if (!document.RootElement.TryGetProperty("security_domains", out var domains) ||
                    domains.ValueKind != JsonValueKind.Array)
                    return null;

                return domains.EnumerateArray()
                    .Select(domain => domain.TryGetProperty("security_parameter", out var parameter)
                        ? parameter.GetString()
                        : null)
                    .FirstOrDefault(parameter => !string.IsNullOrWhiteSpace(parameter));
            }
            catch (JsonException)
            {
                return null;
            }
        }

        private static IReadOnlyList<RlsPolicy> ParseExplicitRlsPolicy(string? policyJson)
        {
            if (string.IsNullOrWhiteSpace(policyJson))
                return Array.Empty<RlsPolicy>();

            try
            {
                using var document = JsonDocument.Parse(policyJson);
                var root = document.RootElement;
                if (root.TryGetProperty("enabled", out var enabled) && enabled.ValueKind == JsonValueKind.False)
                {
                    return new[]
                    {
                        new RlsPolicy(
                            "DisabledScope",
                            "DisabledScope",
                            new HashSet<string>(StringComparer.OrdinalIgnoreCase),
                            new HashSet<string>(StringComparer.OrdinalIgnoreCase),
                            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase))
                    };
                }

                var parameter = root.TryGetProperty("scopeParameter", out var parameterElement)
                    ? parameterElement.GetString()?.Trim().TrimStart('@')
                    : null;
                if (string.IsNullOrWhiteSpace(parameter) ||
                    !root.TryGetProperty("rules", out var rules) ||
                    rules.ValueKind != JsonValueKind.Array)
                    return Array.Empty<RlsPolicy>();

                return rules.EnumerateArray()
                    .Select(rule =>
                    {
                        var table = rule.TryGetProperty("table", out var tableElement) ? tableElement.GetString() : null;
                        var joinTable = rule.TryGetProperty("joinTable", out var joinElement) ? joinElement.GetString() : null;
                        var scopeColumn = rule.TryGetProperty("scopeColumn", out var scopeElement) ? scopeElement.GetString() : null;
                        if (string.IsNullOrWhiteSpace(table) || string.IsNullOrWhiteSpace(scopeColumn))
                            return null;

                        var predicateTable = string.IsNullOrWhiteSpace(joinTable) ? table : joinTable;
                        return new RlsPolicy(
                            parameter,
                            scopeColumn,
                            new HashSet<string>(new[] { table }, StringComparer.OrdinalIgnoreCase),
                            new HashSet<string>(new[] { predicateTable! }, StringComparer.OrdinalIgnoreCase),
                            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase));
                    })
                    .Where(policy => policy != null)
                    .Cast<RlsPolicy>()
                    .ToList();
            }
            catch (JsonException)
            {
                return Array.Empty<RlsPolicy>();
            }
        }

        public async Task<Result<object>> ValidateQueryAsync(
            string sqlQuery,
            Guid semanticLayerId,
            Guid userId,
            CancellationToken cancellationToken = default)
        {
            if (string.IsNullOrWhiteSpace(sqlQuery))
                return Result<object>.Failure("SQL query cannot be empty.");

            var allowedTables = await GetAllowedTablesAsync(semanticLayerId, userId, cancellationToken);
            var sqlWithoutLiteralsAndComments = RemoveCommentsAndStringLiterals(sqlQuery);
            var rlsPolicy = await LoadRlsPolicyAsync(semanticLayerId, cancellationToken);
            var validation = ValidateAndSanitizeSql(sqlQuery, sqlWithoutLiteralsAndComments, allowedTables, rlsPolicy);

            if (validation.Error != null)
                return Result<object>.Failure(validation.Error);

            return Result<object>.Success(new
            {
                validated = true,
                tables = ExtractTableNames(sqlQuery),
                rls = "passed",
                allowedTables = allowedTables.OrderBy(table => table).ToArray()
            });
        }

        private static string[] ExtractTableNames(string sqlQuery)
        {
            var parser = new TSql150Parser(true);
            using var reader = new StringReader(sqlQuery);
            var fragment = parser.Parse(reader, out _);
            var visitor = new TableExtractionVisitor();
            fragment?.Accept(visitor);
            return visitor.Tables.Where(table => !visitor.Ctes.Contains(table)).OrderBy(table => table).ToArray();
        }

        private static string RemoveCommentsAndStringLiterals(string sql)
        {
            // Preserve offsets so ScriptDom fragment ranges still point at the same
            // characters after comments and literals have been masked.
            var masked = sql.ToCharArray();
            var inLineComment = false;
            var inBlockComment = false;
            var inString = false;

            for (var i = 0; i < masked.Length; i++)
            {
                if (inLineComment)
                {
                    if (masked[i] == '\r' || masked[i] == '\n')
                    {
                        inLineComment = false;
                    }
                    else
                    {
                        masked[i] = ' ';
                    }

                    continue;
                }

                if (inBlockComment)
                {
                    if (masked[i] == '*' && i + 1 < masked.Length && masked[i + 1] == '/')
                    {
                        masked[i] = ' ';
                        masked[++i] = ' ';
                        inBlockComment = false;
                    }
                    else if (masked[i] != '\r' && masked[i] != '\n')
                    {
                        masked[i] = ' ';
                    }

                    continue;
                }

                if (inString)
                {
                    if (masked[i] == '\'' && i + 1 < masked.Length && masked[i + 1] == '\'')
                    {
                        masked[i] = ' ';
                        masked[++i] = ' ';
                    }
                    else if (masked[i] == '\'')
                    {
                        masked[i] = ' ';
                        inString = false;
                    }
                    else
                    {
                        masked[i] = ' ';
                    }

                    continue;
                }

                if (masked[i] == '-' && i + 1 < masked.Length && masked[i + 1] == '-')
                {
                    masked[i] = ' ';
                    masked[++i] = ' ';
                    inLineComment = true;
                }
                else if (masked[i] == '/' && i + 1 < masked.Length && masked[i + 1] == '*')
                {
                    masked[i] = ' ';
                    masked[++i] = ' ';
                    inBlockComment = true;
                }
                else if (masked[i] == '\'')
                {
                    masked[i] = ' ';
                    inString = true;
                }
            }

            return new string(masked);
        }

        private (string CleanSql, string? Error) ValidateAndSanitizeSql(
            string originalSql,
            string safeSql,
            HashSet<string> allowedTables,
            IReadOnlyList<RlsPolicy> rlsPolicies)
        {
            var parser = new TSql150Parser(true);
            using var reader = new StringReader(originalSql);
            var fragment = parser.Parse(reader, out IList<ParseError> errors);

            if (errors.Count > 0)
            {
                return (originalSql, $"SQL_SYNTAX_ERROR: {errors.First().Message}");
            }

            if (fragment is TSqlScript script && script.Batches.SelectMany(b => b.Statements).Count() > 1)
            {
                return (originalSql, "SQL_VALIDATION_FAILED: Multiple SQL statements are strictly prohibited.");
            }

            var upperSafeSql = safeSql.ToUpperInvariant();
            var trimmedSafeSql = upperSafeSql.TrimStart();

            if (!trimmedSafeSql.StartsWith("SELECT") && !trimmedSafeSql.StartsWith("WITH"))
            {
                return (originalSql, "SQL_VALIDATION_FAILED: Only SELECT and WITH queries are allowed.");
            }

            foreach (var keyword in _forbiddenKeywords)
            {
                var pattern = keyword.EndsWith("_") ? $@"\b{keyword}" : $@"\b{keyword}\b";
                if (Regex.IsMatch(upperSafeSql, pattern))
                {
                    return (originalSql, "SQL_VALIDATION_FAILED: The query contains forbidden operations or keywords.");
                }
            }

            var visitor = new TableExtractionVisitor();
            fragment.Accept(visitor);

            var actualTables = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var table in visitor.Tables)
            {
                if (!visitor.Ctes.Contains(table))
                {
                    actualTables.Add(table);
                }
            }

            foreach (var tableName in actualTables)
            {
                if (!allowedTables.Contains(tableName))
                {
                    return (originalSql, $"SQL_VALIDATION_FAILED: Access to table '{tableName}' is not allowed or it is disabled by Admin.");
                }
            }

            var rlsError = ValidateRlsMapping(upperSafeSql, actualTables, fragment, rlsPolicies);
            if (rlsError != null)
            {
                return (originalSql, rlsError);
            }

            return (originalSql, null);
        }

        private async Task<IReadOnlyList<RlsPolicy>> LoadRlsPolicyAsync(
            Guid semanticLayerId,
            CancellationToken cancellationToken)
        {
            using var scope = _scopeFactory.CreateScope();
            var dbContext = scope.ServiceProvider.GetRequiredService<IApplicationDbContext>();

            var explicitPolicyJson = await dbContext.SemanticLayers
                .AsNoTracking()
                .Where(layer => layer.Id == semanticLayerId)
                .Select(layer => layer.RlsPolicyJson)
                .FirstOrDefaultAsync(cancellationToken);

            if (!string.IsNullOrWhiteSpace(explicitPolicyJson))
            {
                try
                {
                    var explicitPolicies = ParseExplicitRlsPolicy(explicitPolicyJson);
                    if (explicitPolicies.Count > 0)
                        return explicitPolicies;
                }
                catch (JsonException)
                {
                    return Array.Empty<RlsPolicy>();
                }
            }

            var contentJson = await dbContext.SemanticRevisions
                .AsNoTracking()
                .Where(revision => revision.SemanticLayerId == semanticLayerId &&
                    (revision.Status == "Approved" || revision.Status == "Active"))
                .OrderByDescending(revision => revision.VersionNumber)
                .Select(revision => revision.ContentJson)
                .FirstOrDefaultAsync(cancellationToken);

            if (string.IsNullOrWhiteSpace(contentJson))
                return Array.Empty<RlsPolicy>();

            try
            {
                using var document = JsonDocument.Parse(contentJson);
                if (!document.RootElement.TryGetProperty("security_domains", out var domains) ||
                    domains.ValueKind != JsonValueKind.Array)
                    return Array.Empty<RlsPolicy>();

                var policies = new List<RlsPolicy>();
                foreach (var domain in domains.EnumerateArray())
                {
                    var parameter = domain.TryGetProperty("security_parameter", out var parameterElement)
                        ? parameterElement.GetString()?.Trim().TrimStart('@')
                        : null;
                    var canonicalRoot = domain.TryGetProperty("canonical_root", out var rootElement)
                        ? rootElement.GetString()
                        : null;

                    if (string.IsNullOrWhiteSpace(parameter) || string.IsNullOrWhiteSpace(canonicalRoot))
                        continue;

                    var rootParts = canonicalRoot.Split('.', 2, StringSplitOptions.TrimEntries);
                    if (rootParts.Length != 2)
                        continue;

                    var targets = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    var predicateTables = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { rootParts[0] };
                    var requiredJoins = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

                    if (domain.TryGetProperty("propagation_paths", out var paths) &&
                        paths.ValueKind == JsonValueKind.Array)
                    {
                        foreach (var path in paths.EnumerateArray())
                        {
                            if (path.TryGetProperty("target_table", out var targetElement))
                            {
                                var target = targetElement.GetString();
                                if (!string.IsNullOrWhiteSpace(target))
                                    targets.Add(target);
                            }

                            if (path.TryGetProperty("predicate", out var predicateElement))
                                AddPredicateTable(predicateElement.GetString(), parameter, predicateTables);

                            if (path.TryGetProperty("joins", out var joins) && joins.ValueKind == JsonValueKind.Array)
                            {
                                foreach (var join in joins.EnumerateArray())
                                {
                                    var table = join.TryGetProperty("table", out var tableElement)
                                        ? tableElement.GetString()
                                        : null;
                                    var condition = join.TryGetProperty("condition", out var conditionElement)
                                        ? conditionElement.GetString()
                                        : null;
                                    if (!string.IsNullOrWhiteSpace(table) && !string.IsNullOrWhiteSpace(condition))
                                        requiredJoins[table] = condition;
                                }
                            }
                        }
                    }

                    if (targets.Count == 0)
                        targets.Add(rootParts[0]);

                    policies.Add(new RlsPolicy(
                        parameter,
                        rootParts[1],
                        targets,
                        predicateTables,
                        requiredJoins));
                }

                return policies;
            }
            catch (JsonException ex)
            {
                _logger.LogWarning(ex, "The active semantic revision contains invalid RLS metadata for layer {LayerId}.", semanticLayerId);
                return Array.Empty<RlsPolicy>();
            }
        }

        private static void AddPredicateTable(
            string? predicate,
            string parameter,
            ISet<string> predicateTables)
        {
            if (string.IsNullOrWhiteSpace(predicate))
                return;

            var match = Regex.Match(
                predicate,
                $@"(?<table>[A-Za-z_][A-Za-z0-9_]*)\s*\.\s*[A-Za-z_][A-Za-z0-9_]*\s*=\s*@?{Regex.Escape(parameter)}\b",
                RegexOptions.IgnoreCase);

            if (match.Success)
                predicateTables.Add(match.Groups["table"].Value);
        }

        private string? ValidateRlsMapping(
            string upperSafeSql,
            HashSet<string> actualTables,
            TSqlFragment fragment,
            IReadOnlyList<RlsPolicy> rlsPolicies)
        {
            if (rlsPolicies.Count > 0)
                return ValidateConfiguredRlsMapping(upperSafeSql, actualTables, fragment, rlsPolicies);

            var sakilaTables = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            {
                "STORE", "STAFF", "CUSTOMER", "INVENTORY", "RENTAL", "PAYMENT"
            };

            var usesSakilaRules = actualTables.Any(sakilaTables.Contains) ||
                                  Regex.IsMatch(upperSafeSql, @"\b@USERSTOREID\b", RegexOptions.IgnoreCase);

            return usesSakilaRules
                ? ValidateSakilaRlsMapping(upperSafeSql, actualTables, fragment, sakilaTables)
                : ValidateLegacyRlsMapping(upperSafeSql, actualTables, fragment);
        }

        private string? ValidateConfiguredRlsMapping(
            string upperSafeSql,
            HashSet<string> actualTables,
            TSqlFragment fragment,
            IReadOnlyList<RlsPolicy> rlsPolicies)
        {
            foreach (var policy in rlsPolicies.Where(policy => actualTables.Overlaps(policy.TargetTables)))
            {
                if (!Regex.IsMatch(upperSafeSql, $@"\b@?{Regex.Escape(policy.ParameterName)}\b", RegexOptions.IgnoreCase))
                    return $"RLS_ERROR: Every protected query must use @{policy.ParameterName} from the configured semantic-layer policy.";

                var queryVisitor = new RlsQueryVisitor(
                    upperSafeSql,
                    policy.TargetTables,
                    policy.ParameterName,
                    policy.ScopeColumnName,
                    policy.PredicateTables);
                fragment.Accept(queryVisitor);

                if (queryVisitor.HasUnsafeJoin || Regex.IsMatch(upperSafeSql, @"\bCROSS\s+JOIN\b", RegexOptions.IgnoreCase))
                    return "RLS_ERROR: CROSS JOIN and comma joins are not allowed for protected data.";

                foreach (var query in queryVisitor.QueriesWithProtectedTables)
                {
                    if (!query.HasBranchPredicate)
                        return $"RLS_ERROR: The query must apply the configured row-security predicate using @{policy.ParameterName}.";
                }
            }

            return null;
        }

        private sealed record RlsPolicy(
            string ParameterName,
            string ScopeColumnName,
            HashSet<string> TargetTables,
            HashSet<string> PredicateTables,
            Dictionary<string, string> RequiredJoins);

        private string? ValidateSakilaRlsMapping(
            string upperSafeSql,
            HashSet<string> actualTables,
            TSqlFragment fragment,
            HashSet<string> sakilaTables)
        {
            var queryVisitor = new RlsQueryVisitor(
                upperSafeSql,
                sakilaTables,
                "UserStoreId",
                "store_id",
                sakilaTables);
            fragment.Accept(queryVisitor);

            if (queryVisitor.HasUnsafeJoin || Regex.IsMatch(upperSafeSql, @"\bCROSS\s+JOIN\b", RegexOptions.IgnoreCase))
                return "RLS_ERROR: CROSS JOIN and comma joins are not allowed for protected data.";

            if (!Regex.IsMatch(upperSafeSql, @"\b@USERSTOREID\b", RegexOptions.IgnoreCase))
                return "RLS_ERROR: Every Sakila query that reads protected data must filter store_id by @UserStoreId.";

            foreach (var query in queryVisitor.QueriesWithProtectedTables)
            {
                if (!query.HasBranchPredicate)
                    return "RLS_ERROR: Every Sakila query scope that reads protected data must filter store_id by @UserStoreId.";
            }

            var usesRental = actualTables.Contains("RENTAL");
            var usesPayment = actualTables.Contains("PAYMENT");

            if (usesRental &&
                (!actualTables.Contains("INVENTORY") ||
                 !Regex.IsMatch(upperSafeSql, @"\bJOIN\s+INVENTORY\b[\s\S]*\bINVENTORY_ID\b[\s\S]*=\s*[A-Z0-9_]+\.INVENTORY_ID\b", RegexOptions.IgnoreCase)))
            {
                return "RLS_ERROR: For 'rental', use INNER JOIN inventory through inventory_id and filter inventory.store_id = @UserStoreId.";
            }

            if (usesPayment &&
                (!actualTables.Contains("CUSTOMER") ||
                 !Regex.IsMatch(upperSafeSql, @"\bJOIN\s+CUSTOMER\b[\s\S]*\bCUSTOMER_ID\b[\s\S]*=\s*[A-Z0-9_]+\.CUSTOMER_ID\b", RegexOptions.IgnoreCase)))
            {
                return "RLS_ERROR: For 'payment', use INNER JOIN customer through customer_id and filter customer.store_id = @UserStoreId.";
            }

            return null;
        }

        private string? ValidateLegacyRlsMapping(
            string upperSafeSql,
            HashSet<string> actualTables,
            TSqlFragment fragment)
        {
            var protectedTables = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            {
                "LOANS", "CUSTOMERS", "TRANSACTIONS", "CARDS", "MERCHANTS", "ACCOUNTS"
            };

            var queryVisitor = new RlsQueryVisitor(
                upperSafeSql,
                protectedTables,
                "UserBranchId",
                "branch_id",
                new HashSet<string>(new[] { "ACCOUNTS", "BRANCHES" }, StringComparer.OrdinalIgnoreCase));
            fragment.Accept(queryVisitor);

            if (queryVisitor.HasUnsafeJoin || Regex.IsMatch(upperSafeSql, @"\bCROSS\s+JOIN\b", RegexOptions.IgnoreCase))
            {
                return "RLS_ERROR: CROSS JOIN and comma joins are not allowed for protected data.";
            }

            foreach (var query in queryVisitor.QueriesWithProtectedTables)
            {
                if (!query.HasBranchPredicate)
                {
                    return "RLS_ERROR: Every query scope that reads protected data must filter BranchId by @UserBranchId.";
                }
            }

            var usesLoans = actualTables.Contains("LOANS");
            var usesCustomers = actualTables.Contains("CUSTOMERS");
            var usesTransactions = actualTables.Contains("TRANSACTIONS");
            var usesCards = actualTables.Contains("CARDS");
            var usesMerchants = actualTables.Contains("MERCHANTS");

            if (usesLoans &&
               (!actualTables.Contains("CUSTOMERS") ||
                !actualTables.Contains("ACCOUNTS") ||
                !actualTables.Contains("BRANCHES") ||
                !Regex.IsMatch(upperSafeSql, @"\b(?:BRANCHES|B)\.BRANCH_ID\s*=\s*@USERBRANCHID\b")))
            {
                return "RLS_ERROR: For 'loans', use loans -> customers -> accounts -> branches and filter branches.branch_id = @UserBranchId.";
            }

            if (usesMerchants &&
               (!actualTables.Contains("TRANSACTIONS") || !actualTables.Contains("ACCOUNTS")))
            {
                return "RLS_ERROR: For 'merchants' table, you MUST strictly enforce this rule: INNER JOIN transactions ON merchants.merchant_id = transactions.merchant_id INNER JOIN accounts ON transactions.account_id = accounts.account_id WHERE accounts.branch_id = @UserBranchId";
            }

            if (usesCustomers && !actualTables.Contains("ACCOUNTS") && !usesLoans)
            {
                return "RLS_ERROR: For 'customers' table, you MUST strictly enforce this rule: INNER JOIN accounts ON customers.customer_id = accounts.customer_id WHERE accounts.branch_id = @UserBranchId";
            }

            if ((usesTransactions || usesCards) && !actualTables.Contains("ACCOUNTS") && !usesMerchants)
            {
                return "RLS_ERROR: For 'transactions' or 'cards' tables, you MUST strictly enforce this rule: INNER JOIN accounts ON [table].account_id = accounts.account_id WHERE accounts.branch_id = @UserBranchId";
            }

            return null;
        }

        private static class BranchPredicateExpressionValidator
        {
            public static bool GuaranteesBranchIsolation(
                BooleanExpression expression,
                TableExtractionVisitor tableVisitor,
                string parameterName,
                string expectedColumnName,
                HashSet<string> predicateTables)
            {
                return expression switch
                {
                    BooleanParenthesisExpression parenthesis =>
                        GuaranteesBranchIsolation(parenthesis.Expression, tableVisitor, parameterName, expectedColumnName, predicateTables),

                    BooleanComparisonExpression comparison =>
                        IsBranchPredicate(comparison, tableVisitor, parameterName, expectedColumnName, predicateTables),

                    BooleanBinaryExpression binary when binary.BinaryExpressionType ==
                        BooleanBinaryExpressionType.And =>
                        GuaranteesBranchIsolation(binary.FirstExpression, tableVisitor, parameterName, expectedColumnName, predicateTables) ||
                        GuaranteesBranchIsolation(binary.SecondExpression, tableVisitor, parameterName, expectedColumnName, predicateTables),

                    BooleanBinaryExpression binary when binary.BinaryExpressionType ==
                        BooleanBinaryExpressionType.Or =>
                        GuaranteesBranchIsolation(binary.FirstExpression, tableVisitor, parameterName, expectedColumnName, predicateTables) &&
                        GuaranteesBranchIsolation(binary.SecondExpression, tableVisitor, parameterName, expectedColumnName, predicateTables),

                    _ => false
                };
            }

            private static bool IsBranchPredicate(
                BooleanComparisonExpression comparison,
                TableExtractionVisitor tableVisitor,
                string parameterName,
                string expectedColumnName,
                HashSet<string> predicateTables)
            {
                if (comparison.ComparisonType != BooleanComparisonType.Equals)
                {
                    return false;
                }

                ColumnReferenceExpression? column = null;
                VariableReference? variable = null;

                if (comparison.FirstExpression is ColumnReferenceExpression firstColumn &&
                    comparison.SecondExpression is VariableReference secondVariable)
                {
                    column = firstColumn;
                    variable = secondVariable;
                }
                else if (comparison.SecondExpression is ColumnReferenceExpression secondColumn &&
                         comparison.FirstExpression is VariableReference firstVariable)
                {
                    column = secondColumn;
                    variable = firstVariable;
                }

                if (column == null || variable == null ||
                    !string.Equals(variable.Name.TrimStart('@'), parameterName, StringComparison.OrdinalIgnoreCase))
                {
                    return false;
                }

                var identifiers = column.MultiPartIdentifier?.Identifiers;
                var actualColumnName = identifiers?.LastOrDefault()?.Value;
                if (!string.Equals(actualColumnName, expectedColumnName, StringComparison.OrdinalIgnoreCase))
                {
                    return false;
                }

                var alias = identifiers is { Count: > 1 }
                    ? identifiers[^2].Value
                    : null;

                return alias != null &&
                       tableVisitor.TableAliases.TryGetValue(alias, out var physicalTable) &&
                       predicateTables.Contains(physicalTable);
            }
        }

        private sealed class RlsQueryVisitor : TSqlFragmentVisitor
        {
            private readonly string _sql;
            private readonly HashSet<string> _protectedTables;
            private readonly string _parameterName;
            private readonly string _columnName;
            private readonly HashSet<string> _predicateTables;

            public RlsQueryVisitor(
                string sql,
                HashSet<string> protectedTables,
                string parameterName,
                string expectedColumnName,
                HashSet<string> predicateTables)
            {
                _sql = sql;
                _protectedTables = protectedTables;
                _parameterName = parameterName;
                _columnName = expectedColumnName;
                _predicateTables = predicateTables;
            }

            public List<(string Sql, bool HasBranchPredicate)> QueriesWithProtectedTables { get; } = new();
            public bool HasUnsafeJoin { get; private set; }

            public override void ExplicitVisit(QuerySpecification node)
            {
                if (node.FromClause?.TableReferences.Count > 1)
                {
                    HasUnsafeJoin = true;
                }

                var joinVisitor = new JoinPredicateVisitor();
                node.Accept(joinVisitor);
                if (joinVisitor.HasInvalidJoinPredicate)
                {
                    HasUnsafeJoin = true;
                }

                var start = Math.Max(0, node.StartOffset);
                var length = Math.Min(node.FragmentLength, _sql.Length - start);
                var querySql = length > 0 ? _sql.Substring(start, length) : string.Empty;

                // Only inspect tables belonging to this query scope. Nested
                // subqueries/CTEs are visited separately by this visitor; if
                // their tables are included here too, the outer scope can be
                // incorrectly rejected for not having its own branch filter.
                var tableVisitor = new DirectTableExtractionVisitor();
                node.Accept(tableVisitor);
                var hasProtectedTable = tableVisitor.Tables.Any(_protectedTables.Contains);

                if (hasProtectedTable)
                {
                    var hasBranchPredicate = node.WhereClause?.SearchCondition is { } condition
                        && BranchPredicateExpressionValidator.GuaranteesBranchIsolation(
                            condition,
                            tableVisitor,
                            _parameterName,
                            _columnName,
                            _predicateTables);

                    QueriesWithProtectedTables.Add((querySql, hasBranchPredicate));
                }

                base.ExplicitVisit(node);
            }

            private sealed class JoinPredicateVisitor : TSqlFragmentVisitor
            {
                public bool HasInvalidJoinPredicate { get; private set; }

                public override void ExplicitVisit(QualifiedJoin node)
                {
                    if (node.SearchCondition == null)
                    {
                        HasInvalidJoinPredicate = true;
                    }
                    else
                    {
                        var comparisonVisitor = new ColumnEqualityVisitor();
                        node.SearchCondition.Accept(comparisonVisitor);
                        if (!comparisonVisitor.HasColumnEquality)
                        {
                            HasInvalidJoinPredicate = true;
                        }
                    }

                    base.ExplicitVisit(node);
                }
            }

            private sealed class ColumnEqualityVisitor : TSqlFragmentVisitor
            {
                public bool HasColumnEquality { get; private set; }

                public override void ExplicitVisit(BooleanComparisonExpression node)
                {
                    if (node.ComparisonType == BooleanComparisonType.Equals &&
                        node.FirstExpression is ColumnReferenceExpression &&
                        node.SecondExpression is ColumnReferenceExpression)
                    {
                        HasColumnEquality = true;
                    }

                    base.ExplicitVisit(node);
                }
            }

        }

        private class TableExtractionVisitor : TSqlFragmentVisitor
        {
            public HashSet<string> Tables { get; } = new(StringComparer.OrdinalIgnoreCase);
            public HashSet<string> Ctes { get; } = new(StringComparer.OrdinalIgnoreCase);
            public Dictionary<string, string> TableAliases { get; } = new(StringComparer.OrdinalIgnoreCase);

            public override void ExplicitVisit(CommonTableExpression node)
            {
                if (node.ExpressionName != null)
                {
                    Ctes.Add(node.ExpressionName.Value);
                }
                base.ExplicitVisit(node);
            }

            public override void ExplicitVisit(NamedTableReference node)
            {
                if (node.SchemaObject != null && node.SchemaObject.BaseIdentifier != null)
                {
                    var tableName = node.SchemaObject.BaseIdentifier.Value;
                    Tables.Add(tableName);
                    TableAliases[tableName] = tableName;

                    if (node.Alias != null && !string.IsNullOrWhiteSpace(node.Alias.Value))
                    {
                        TableAliases[node.Alias.Value] = tableName;
                    }
                }
                base.ExplicitVisit(node);
            }
        }

        private sealed class DirectTableExtractionVisitor : TableExtractionVisitor
        {
            private bool _rootQueryVisited;

            public override void ExplicitVisit(QuerySpecification node)
            {
                if (_rootQueryVisited)
                {
                    return;
                }

                _rootQueryVisited = true;
                base.ExplicitVisit(node);
            }
        }
    }
}
