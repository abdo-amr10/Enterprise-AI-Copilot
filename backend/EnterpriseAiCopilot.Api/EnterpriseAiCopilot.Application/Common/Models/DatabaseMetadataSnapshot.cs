namespace EnterpriseAiCopilot.Application.Common.Models;

public sealed class DatabaseMetadataSnapshot
{
    public string DatabaseName { get; init; } = string.Empty;
    public DateTime SyncedAtUtc { get; init; }
    public IReadOnlyList<DatabaseTableMetadata> Tables { get; init; } = Array.Empty<DatabaseTableMetadata>();
    public IReadOnlyList<DatabaseRelationshipMetadata> Relationships { get; init; } = Array.Empty<DatabaseRelationshipMetadata>();
}

public sealed class DatabaseTableMetadata
{
    public string Schema { get; init; } = "dbo";
    public string Name { get; init; } = string.Empty;
    public IReadOnlyList<DatabaseColumnMetadata> Columns { get; init; } = Array.Empty<DatabaseColumnMetadata>();
}

public sealed class DatabaseColumnMetadata
{
    public string Name { get; init; } = string.Empty;
    public string DataType { get; init; } = string.Empty;
    public bool IsNullable { get; init; }
    public bool IsPrimaryKey { get; init; }
}

public sealed class DatabaseRelationshipMetadata
{
    public string FromSchema { get; init; } = "dbo";
    public string FromTable { get; init; } = string.Empty;
    public string FromColumn { get; init; } = string.Empty;
    public string ToSchema { get; init; } = "dbo";
    public string ToTable { get; init; } = string.Empty;
    public string ToColumn { get; init; } = string.Empty;
}
