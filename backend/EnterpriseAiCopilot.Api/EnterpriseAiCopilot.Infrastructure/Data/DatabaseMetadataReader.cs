using Dapper;
using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.Common.Models;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.Configuration;

namespace EnterpriseAiCopilot.Infrastructure.Data;

public sealed class DatabaseMetadataReader : IDatabaseMetadataReader
{
    private readonly IConfiguration _configuration;

    public DatabaseMetadataReader(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public Task<Result<DatabaseMetadataSnapshot>> ReadTargetAsync(CancellationToken cancellationToken = default)
    {
        return ReadAsync(_configuration.GetConnectionString("TargetConnection") ?? string.Empty, cancellationToken);
    }

    public async Task<Result<DatabaseMetadataSnapshot>> ReadAsync(
        string connectionString,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(connectionString))
            return Result<DatabaseMetadataSnapshot>.Failure("DATABASE_CONFIGURATION_ERROR: Target connection is missing.");

        try
        {
            await using var connection = new SqlConnection(connectionString);
            await connection.OpenAsync(cancellationToken);

            const string tableSql = """
                SELECT TABLE_SCHEMA AS [Schema], TABLE_NAME AS [Name]
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_SCHEMA, TABLE_NAME;
                """;

            const string columnSql = """
                SELECT c.TABLE_SCHEMA AS [Schema], c.TABLE_NAME AS [TableName],
                       c.COLUMN_NAME AS [Name], c.DATA_TYPE AS [DataType],
                       CAST(CASE WHEN c.IS_NULLABLE = 'YES' THEN 1 ELSE 0 END AS bit) AS IsNullable,
                       CAST(CASE WHEN EXISTS (
                           SELECT 1
                           FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
                           INNER JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                               ON tc.CONSTRAINT_NAME = k.CONSTRAINT_NAME
                              AND tc.TABLE_SCHEMA = k.TABLE_SCHEMA
                              AND tc.TABLE_NAME = k.TABLE_NAME
                           WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                             AND k.TABLE_SCHEMA = c.TABLE_SCHEMA
                             AND k.TABLE_NAME = c.TABLE_NAME
                             AND k.COLUMN_NAME = c.COLUMN_NAME
                       ) THEN 1 ELSE 0 END AS bit) AS IsPrimaryKey
                FROM INFORMATION_SCHEMA.COLUMNS c
                ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION;
                """;

            const string relationshipSql = """
                SELECT OBJECT_SCHEMA_NAME(fk.parent_object_id) AS FromSchema,
                       OBJECT_NAME(fk.parent_object_id) AS FromTable,
                       pc.name AS FromColumn,
                       OBJECT_SCHEMA_NAME(fk.referenced_object_id) AS ToSchema,
                       OBJECT_NAME(fk.referenced_object_id) AS ToTable,
                       rc.name AS ToColumn
                FROM sys.foreign_keys fk
                INNER JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
                INNER JOIN sys.columns pc ON pc.object_id = fk.parent_object_id AND pc.column_id = fkc.parent_column_id
                INNER JOIN sys.columns rc ON rc.object_id = fk.referenced_object_id AND rc.column_id = fkc.referenced_column_id
                ORDER BY FromSchema, FromTable, ToSchema, ToTable;
                """;

            var tables = (await connection.QueryAsync<RawTable>(new CommandDefinition(tableSql, cancellationToken: cancellationToken))).ToList();
            var columns = (await connection.QueryAsync<RawColumn>(new CommandDefinition(columnSql, cancellationToken: cancellationToken))).ToList();
            var relationships = (await connection.QueryAsync<DatabaseRelationshipMetadata>(new CommandDefinition(relationshipSql, cancellationToken: cancellationToken))).ToList();

            var metadataTables = tables.Select(table => new DatabaseTableMetadata
            {
                Schema = table.Schema,
                Name = table.Name,
                Columns = columns
                    .Where(column => string.Equals(column.Schema, table.Schema, StringComparison.OrdinalIgnoreCase) &&
                                     string.Equals(column.TableName, table.Name, StringComparison.OrdinalIgnoreCase))
                    .Select(column => new DatabaseColumnMetadata
                    {
                        Name = column.Name,
                        DataType = column.DataType,
                        IsNullable = column.IsNullable,
                        IsPrimaryKey = column.IsPrimaryKey
                    })
                    .ToList()
            }).ToList();

            var builder = new SqlConnectionStringBuilder(connectionString);
            return Result<DatabaseMetadataSnapshot>.Success(new DatabaseMetadataSnapshot
            {
                DatabaseName = builder.InitialCatalog,
                SyncedAtUtc = DateTime.UtcNow,
                Tables = metadataTables,
                Relationships = relationships
            });
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception ex)
        {
            return Result<DatabaseMetadataSnapshot>.Failure($"DATABASE_METADATA_ERROR: {ex.Message}");
        }
    }

    private sealed class RawTable
    {
        public string Schema { get; set; } = "dbo";
        public string Name { get; set; } = string.Empty;
    }

    private sealed class RawColumn
    {
        public string Schema { get; set; } = "dbo";
        public string TableName { get; set; } = string.Empty;
        public string Name { get; set; } = string.Empty;
        public string DataType { get; set; } = string.Empty;
        public bool IsNullable { get; set; }
        public bool IsPrimaryKey { get; set; }
    }
}
