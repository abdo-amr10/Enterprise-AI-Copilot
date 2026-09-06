using EnterpriseAiCopilot.Application.Common.Models;

namespace EnterpriseAiCopilot.Application.Common.Interfaces;

public interface ISemanticIndexStorage
{
    Task<Result<bool>> SaveArtifactBundleAsync(Guid layerId, Guid revisionId, Stream faissStream, string indexMetadataJson, string documentMetadataJson, CancellationToken cancellationToken = default);
    Task<Result<byte[]>> GetArtifactBundleZipAsync(Guid layerId, Guid revisionId, CancellationToken cancellationToken = default);
    Task<bool> ArtifactExistsAsync(Guid layerId, Guid revisionId, CancellationToken cancellationToken = default);
    Task<Result<bool>> DeleteRevisionArtifactAsync(Guid layerId, Guid revisionId, CancellationToken cancellationToken = default);
    Task<Result<bool>> DeleteLayerArtifactsAsync(Guid layerId, CancellationToken cancellationToken = default);
}
