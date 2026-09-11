using EnterpriseAiCopilot.Application.Common.Models;

namespace EnterpriseAiCopilot.Application.Common.Interfaces;

public interface IDatabaseMetadataReader
{
    Task<Result<DatabaseMetadataSnapshot>> ReadTargetAsync(CancellationToken cancellationToken = default);

    Task<Result<DatabaseMetadataSnapshot>> ReadAsync(
        string connectionString,
        CancellationToken cancellationToken = default);
}
