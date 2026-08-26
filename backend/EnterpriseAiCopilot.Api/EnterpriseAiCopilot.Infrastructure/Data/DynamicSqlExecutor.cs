using System;
using System.Collections.Generic;
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

        private async Task<HashSet<string>> GetAllowedTablesAsync()
        {
            if (!_cache.TryGetValue("AllowedTablesCacheKey", out HashSet<string>? allowedTables) || allowedTables == null)
            {
                using var scope = _scopeFactory.CreateScope();
                var dbContext = scope.ServiceProvider.GetRequiredService<IApplicationDbContext>();

                var tablesFromDb = await dbContext.AllowedTables
                    .Where(t => t.IsAllowed)
                    .Select(t => t.TableName.ToLower())
                    .ToListAsync();

                allowedTables = new HashSet<string>(tablesFromDb, StringComparer.OrdinalIgnoreCase);
                _cache.Set("AllowedTablesCacheKey", allowedTables, TimeSpan.FromHours(24));
            }

            return allowedTables;
        }

        public async Task<Result<object>> ExecuteQueryAsync(
            string sqlQuery,
            string branchId,
            CancellationToken cancellationToken = default)
        {
            if (string.IsNullOrWhiteSpace(sqlQuery))
            {
                return Result<object>.Failure("SQL query cannot be empty.");
            }

            var allowedTables = await GetAllowedTablesAsync();

            var validation = ValidateAndSanitizeSql(sqlQuery, allowedTables);

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
                    validation.CleanSql,
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

        private static string RemoveSqlComments(string sql)
        {
            sql = Regex.Replace(sql, @"--.*?$", "", RegexOptions.Multiline);
            sql = Regex.Replace(sql, @"/\*[\s\S]*?\*/", "");
            return sql;
        }

        private (string CleanSql, string? Error) ValidateAndSanitizeSql(string sqlQuery, HashSet<string> allowedTables)
        {
            var cleanSql = RemoveSqlComments(sqlQuery).Trim();
            var upperSql = cleanSql.ToUpperInvariant();
            var trimmedSql = upperSql.TrimStart();

            if (cleanSql.Contains(';'))
            {
                return (cleanSql, "SQL_VALIDATION_FAILED: Multiple SQL statements are strictly prohibited.");
            }

            if (!trimmedSql.StartsWith("SELECT"))
            {
                return (cleanSql, "SQL_VALIDATION_FAILED: Only SELECT queries are allowed.");
            }

            foreach (var keyword in _forbiddenKeywords)
            {
                var pattern = keyword.EndsWith("_") ? $@"\b{keyword}" : $@"\b{keyword}\b";
                if (Regex.IsMatch(upperSql, pattern))
                {
                    return (cleanSql, "SQL_VALIDATION_FAILED: The query contains forbidden operations or keywords.");
                }
            }

            if (Regex.IsMatch(upperSql, @"\bOR\b"))
            {
                return (cleanSql, "SQL_VALIDATION_FAILED: OR conditions are not allowed in AI-generated SQL.");
            }

            var hasRlsPredicate = Regex.IsMatch(
                cleanSql,
                @"\b[A-Za-z_][A-Za-z0-9_]*\.(?:BranchId|branch_id)\s*=\s*@UserBranchId\b",
                RegexOptions.IgnoreCase);

            if (!hasRlsPredicate)
            {
                return (cleanSql, "RLS_ERROR: Query must include a fully qualified branch filter predicate (e.g., accounts.branch_id = @UserBranchId). Unqualified columns are not allowed.");
            }


            var rlsError = ValidateRlsMapping(upperSql);
            if (rlsError != null)
            {
                return (cleanSql, rlsError);
            }

            var tableMatches = Regex.Matches(
                cleanSql,
                @"\b(?:FROM|JOIN)\s+(?:\[[^\]]+\]\.)?\[?([A-Za-z0-9_]+)\]?",
                RegexOptions.IgnoreCase);

            foreach (Match match in tableMatches)
            {
                if (!match.Success || match.Groups.Count <= 1) continue;

                var tableName = match.Groups[1].Value.ToLower();

                if (!allowedTables.Contains(tableName))
                {
                    return (cleanSql, $"SQL_VALIDATION_FAILED: Access to table '{tableName}' is not allowed or it is disabled by Admin.");
                }
            }

            return (cleanSql, null);
        }

        private string? ValidateRlsMapping(string upperSql)
        {
            if (upperSql.Contains("LOANS") &&
               (!upperSql.Contains("JOIN CUSTOMERS") ||
                !upperSql.Contains("JOIN ACCOUNTS") ||
                !upperSql.Contains("JOIN BRANCHES") ||
                !Regex.IsMatch(upperSql, @"\b(?:BRANCHES|B)\.BRANCH_ID\s*=\s*@USERBRANCHID\b")))
            {
                return "RLS_ERROR: For 'loans', use loans -> customers -> accounts -> branches and filter branches.branch_id = @UserBranchId.";
            }

            if (upperSql.Contains("MERCHANTS") &&
               (!upperSql.Contains("JOIN TRANSACTIONS") || !upperSql.Contains("JOIN ACCOUNTS")))
            {
                return "RLS_ERROR: For 'merchants' table, you MUST strictly enforce this rule: INNER JOIN transactions ON merchants.merchant_id = transactions.merchant_id INNER JOIN accounts ON transactions.account_id = accounts.account_id WHERE accounts.branch_id = @UserBranchId";
            }

            if (upperSql.Contains("CUSTOMERS") &&
                !upperSql.Contains("JOIN ACCOUNTS") && !upperSql.Contains("LOANS"))
            {
                return "RLS_ERROR: For 'customers' table, you MUST strictly enforce this rule: INNER JOIN accounts ON customers.customer_id = accounts.customer_id WHERE accounts.branch_id = @UserBranchId";
            }

            if ((upperSql.Contains("TRANSACTIONS") || upperSql.Contains("CARDS")) &&
                !upperSql.Contains("JOIN ACCOUNTS") && !upperSql.Contains("MERCHANTS"))
            {
                return "RLS_ERROR: For 'transactions' or 'cards' tables, you MUST strictly enforce this rule: INNER JOIN accounts ON [table].account_id = accounts.account_id WHERE accounts.branch_id = @UserBranchId";
            }

            return null;
        }
    }
}