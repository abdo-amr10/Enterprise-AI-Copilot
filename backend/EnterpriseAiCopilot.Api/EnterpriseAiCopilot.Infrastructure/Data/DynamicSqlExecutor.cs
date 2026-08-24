using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Dapper;
using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.Common.Models;

namespace EnterpriseAiCopilot.Infrastructure.Data
{
    public class DynamicSqlExecutor : IDynamicSqlExecutor
    {
        private readonly IConfiguration _configuration;
        private readonly ILogger<DynamicSqlExecutor> _logger;

        private readonly string[] _forbiddenKeywords =
        {
            "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
            "TRUNCATE", "EXEC", "EXECUTE", "CREATE", "GRANT",
            "REVOKE", "XP_", "SP_"
        };

        private readonly HashSet<string> _allowedTables = new(StringComparer.OrdinalIgnoreCase)
        {
            "branches", "accounts", "transactions", "cards", 
            "customers", "loans", "merchants"
        };

        public DynamicSqlExecutor(
            IConfiguration configuration,
            ILogger<DynamicSqlExecutor> logger)
        {
            _configuration = configuration;
            _logger = logger;
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

            var validationError = ValidateAndSanitizeSql(sqlQuery);
            if (validationError != null)
            {
                return Result<object>.Failure(validationError);
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
            catch (OperationCanceledException)
            {
                throw;
            }
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

        private string? ValidateAndSanitizeSql(string sqlQuery)
        {
            if (sqlQuery.Contains(';'))
            {
                var trimmed = sqlQuery.TrimEnd();
                if (!trimmed.EndsWith(';') || trimmed.Count(c => c == ';') > 1)
                {
                    return "SQL_VALIDATION_FAILED: Multiple SQL statements are strictly prohibited.";
                }
            }

            var upperSql = sqlQuery.ToUpperInvariant();
            var trimmedSql = upperSql.TrimStart();

            if (!trimmedSql.StartsWith("SELECT") && !trimmedSql.StartsWith("WITH"))
            {
                return "SQL_VALIDATION_FAILED: Only SELECT and WITH queries are allowed.";
            }

            foreach (var keyword in _forbiddenKeywords)
            {
                var pattern = keyword.EndsWith("_") ? $@"\b{keyword}" : $@"\b{keyword}\b";
                if (Regex.IsMatch(upperSql, pattern))
                {
                    return "SQL_VALIDATION_FAILED: The query contains forbidden operations or keywords.";
                }
            }

            if (!sqlQuery.Contains("@UserBranchId", StringComparison.OrdinalIgnoreCase))
            {
                return "SQL_VALIDATION_FAILED: Security policy violation. Query must include branch filtering (@UserBranchId).";
            }

            var rlsError = ValidateRlsMapping(upperSql);
            if (rlsError != null)
            {
                return rlsError;
            }

            var tableMatches = Regex.Matches(
                sqlQuery,
                @"\b(?:FROM|JOIN)\s+(?:\[[^\]]+\]\.)?\[?([A-Za-z0-9_]+)\]?",
                RegexOptions.IgnoreCase);

            foreach (Match match in tableMatches)
            {
                if (!match.Success || match.Groups.Count <= 1) continue;

                var tableName = match.Groups[1].Value;
                if (!_allowedTables.Contains(tableName))
                {
                    return $"SQL_VALIDATION_FAILED: Access to table '{tableName}' is not allowed.";
                }
            }

            return null;
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
