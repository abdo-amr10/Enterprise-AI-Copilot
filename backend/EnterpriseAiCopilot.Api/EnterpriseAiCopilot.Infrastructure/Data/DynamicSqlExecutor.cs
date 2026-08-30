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
            "REVOKE", "XP_", "SP_", "UNION", "MERGE", "CALL"
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

            var allowedTables = await GetAllowedTablesAsync(semanticLayerId, userId, cancellationToken);

            var sqlWithoutLiteralsAndComments = RemoveCommentsAndStringLiterals(sqlQuery);

            var validation = ValidateAndSanitizeSql(sqlQuery, sqlWithoutLiteralsAndComments, allowedTables);

            if (validation.Error != null)
            {
                return Result<object>.Failure(validation.Error);
            }

            try
            {
                var connectionString = _configuration.GetConnectionString("DefaultConnection");

                if (string.IsNullOrWhiteSpace(connectionString))
                {
                    return Result<object>.Failure("DATABASE_CONFIGURATION_ERROR: Database connection string is missing.");
                }

                await using var connection = new SqlConnection(connectionString);
                await connection.OpenAsync(cancellationToken);

                var parameters = new { UserBranchId = branchId };

                var command = new CommandDefinition(
                    sqlQuery,
                    parameters,
                    commandTimeout: 30,
                    cancellationToken: cancellationToken
                );

                var result = await connection.QueryAsync<dynamic>(command);
                return Result<object>.Success(result.ToList());
            }
            catch (OperationCanceledException) { throw; }
            catch (SqlException ex)
            {
                _logger.LogError(ex, "Database execution error during dynamic SQL execution.");
                return Result<object>.Failure("DATABASE_EXECUTION_ERROR: An error occurred while executing the query.");
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Unexpected error during dynamic SQL execution.");
                return Result<object>.Failure("UNEXPECTED_ERROR: Failed to process query execution.");
            }
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

        private (string CleanSql, string? Error) ValidateAndSanitizeSql(string originalSql, string safeSql, HashSet<string> allowedTables)
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

            if (Regex.IsMatch(upperSafeSql, @"\bOR\b"))
            {
                return (originalSql, "SQL_VALIDATION_FAILED: OR conditions are not allowed in AI-generated SQL.");
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

            var hasRlsPredicate = Regex.IsMatch(
                safeSql,
                @"\b[A-Za-z_][A-Za-z0-9_]*\.(?:BranchId|branch_id)\s*=\s*@UserBranchId\b",
                RegexOptions.IgnoreCase);

            if (!hasRlsPredicate)
            {
                return (originalSql, "RLS_ERROR: Query must include a fully qualified branch filter predicate (e.g., accounts.branch_id = @UserBranchId). Unqualified columns are not allowed.");
            }

            var rlsError = ValidateRlsMapping(upperSafeSql, actualTables, fragment);
            if (rlsError != null)
            {
                return (originalSql, rlsError);
            }

            return (originalSql, null);
        }

        private string? ValidateRlsMapping(
            string upperSafeSql,
            HashSet<string> actualTables,
            TSqlFragment fragment)
        {
            var protectedTables = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            {
                "LOANS", "CUSTOMERS", "TRANSACTIONS", "CARDS", "MERCHANTS", "ACCOUNTS"
            };

            var queryVisitor = new RlsQueryVisitor(upperSafeSql, protectedTables);
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

        private static bool HasQualifiedBranchPredicate(string sql, TableExtractionVisitor tableVisitor)
        {
            var match = Regex.Match(
                sql,
                @"(?:\[(?<alias>[A-Za-z_][A-Za-z0-9_]*)\]|(?<alias>[A-Za-z_][A-Za-z0-9_]*))\s*\.\s*\[?(?:BranchId|branch_id)\]?\s*=\s*@UserBranchId\b",
                RegexOptions.IgnoreCase);

            if (!match.Success)
            {
                return false;
            }

            var alias = match.Groups["alias"].Value;
            return tableVisitor.TableAliases.TryGetValue(alias, out var physicalTable) &&
                   (physicalTable.Equals("ACCOUNTS", StringComparison.OrdinalIgnoreCase) ||
                    physicalTable.Equals("BRANCHES", StringComparison.OrdinalIgnoreCase));
        }

        private sealed class RlsQueryVisitor : TSqlFragmentVisitor
        {
            private readonly string _sql;
            private readonly HashSet<string> _protectedTables;

            public RlsQueryVisitor(string sql, HashSet<string> protectedTables)
            {
                _sql = sql;
                _protectedTables = protectedTables;
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

                var tableVisitor = new TableExtractionVisitor();
                node.Accept(tableVisitor);
                var hasProtectedTable = tableVisitor.Tables.Any(_protectedTables.Contains);

                if (hasProtectedTable)
                {
                    QueriesWithProtectedTables.Add((querySql, HasQualifiedBranchPredicate(querySql, tableVisitor)));
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
    }
}
