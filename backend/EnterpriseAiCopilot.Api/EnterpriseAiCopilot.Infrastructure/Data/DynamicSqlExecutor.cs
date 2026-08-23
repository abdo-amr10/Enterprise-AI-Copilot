using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.Common.Models;
using Dapper;

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
            "branches",
            "accounts",
            "transactions",
            "cards",
            "customers",
            "loans",
            "merchants"
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
            int branchId,
            CancellationToken cancellationToken = default)
        {
            if (string.IsNullOrWhiteSpace(sqlQuery))
                return Result<object>.Failure("SQL query cannot be empty.");

            var validationError = ValidateAndSanitizeSql(sqlQuery);

            if (validationError != null)
                return Result<object>.Failure(validationError);

            try
            {
                var connectionString =
                    _configuration.GetConnectionString("DefaultConnection");

                if (string.IsNullOrWhiteSpace(connectionString))
                    return Result<object>.Failure(
                        "DATABASE_CONFIGURATION_ERROR: Database connection string is missing.");

                await using var connection =
                    new SqlConnection(connectionString);

                await connection.OpenAsync(cancellationToken);

                var parameters = new
                {
                    UserBranchId = branchId
                };

                var command = new CommandDefinition(
                    sqlQuery,
                    parameters,
                    commandTimeout: 30,
                    cancellationToken: cancellationToken
                );

                var result =
                    await connection.QueryAsync<dynamic>(command);

                return Result<object>.Success(result.ToList());
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (SqlException ex)
            {
                _logger.LogError(
                    ex,
                    "Database execution error during dynamic SQL execution.");

                return Result<object>.Failure(
                    "DATABASE_EXECUTION_ERROR: An error occurred while executing the query.");
            }
            catch (Exception ex)
            {
                _logger.LogError(
                    ex,
                    "Unexpected error during dynamic SQL execution.");

                return Result<object>.Failure(
                    "UNEXPECTED_ERROR: Failed to process query execution.");
            }
        }

        private string? ValidateAndSanitizeSql(string sqlQuery)
        {
            if (sqlQuery.Contains(';'))
            {
                var trimmed = sqlQuery.TrimEnd();

                if (!trimmed.EndsWith(';') ||
                    trimmed.Count(c => c == ';') > 1)
                {
                    return "SQL_VALIDATION_FAILED: Multiple SQL statements are strictly prohibited.";
                }
            }

            var upperSql = sqlQuery.ToUpperInvariant();

            var trimmedSql = upperSql.TrimStart();

            if (!trimmedSql.StartsWith("SELECT") &&
                !trimmedSql.StartsWith("WITH"))
            {
                return "SQL_VALIDATION_FAILED: Only SELECT and WITH queries are allowed.";
            }

            foreach (var keyword in _forbiddenKeywords)
            {
                var pattern = keyword.EndsWith("_")
                    ? $@"\b{keyword}"
                    : $@"\b{keyword}\b";

                if (Regex.IsMatch(upperSql, pattern))
                {
                    return "SQL_VALIDATION_FAILED: The query contains forbidden operations or keywords.";
                }
            }

            if (!sqlQuery.Contains(
                    "@UserBranchId",
                    StringComparison.OrdinalIgnoreCase))
            {
                return "SQL_VALIDATION_FAILED: Security policy violation. Query must include branch filtering (@UserBranchId).";
            }

            var tableMatches = Regex.Matches(
                sqlQuery,
                @"\b(?:FROM|JOIN)\s+(?:\[[^\]]+\]\.)?\[?([A-Za-z0-9_]+)\]?",
                RegexOptions.IgnoreCase);

            foreach (Match match in tableMatches)
            {
                if (!match.Success || match.Groups.Count <= 1)
                    continue;

                var tableName = match.Groups[1].Value;

                if (!_allowedTables.Contains(tableName))
                {
                    return $"SQL_VALIDATION_FAILED: Access to table '{tableName}' is not allowed.";
                }
            }

            return null;
        }
    }
}