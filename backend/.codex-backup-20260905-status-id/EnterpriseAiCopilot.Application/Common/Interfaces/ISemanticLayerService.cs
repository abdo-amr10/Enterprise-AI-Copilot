using EnterpriseAiCopilot.Application.Common.Models;
using EnterpriseAiCopilot.Application.DTOs;
using EnterpriseAiCopilot.Application.DTOs.SemanticLayer;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.Common.Interfaces
{
    public interface ISemanticLayerService
    {
        Task<Result<UploadDataSourcesResponse>> UploadDataSourcesAsync(UploadDataSourcesRequest request, CancellationToken cancellationToken = default);
        Task<Result<GenerateDraftResponse>> GenerateDraftAsync(GenerateDraftRequest request, CancellationToken cancellationToken = default);
        Task<Result<ReviewRevisionResponse>> ReviewRevisionAsync(ReviewRevisionRequest request, CancellationToken cancellationToken = default);
        Task<Result<RetrieveSourceFileResponse>> GetSourceFileAsync(Guid fileId, CancellationToken cancellationToken = default);
        Task<Result<SourceFileBinaryResponse>> GetSourceFileBinaryAsync(Guid fileId, CancellationToken cancellationToken = default);
        Task<Result<RetrieveSemanticRevisionResponse>> GetRevisionAsync(Guid revisionId, CancellationToken cancellationToken = default);
        Task<Result<SubmitRevisionResponse>> SubmitRevisionAsync(Guid revisionId, CancellationToken cancellationToken = default);
        Task<Result<SemanticLayerStatusResponse>> GetSemanticLayerStatusAsync(CancellationToken cancellationToken = default);
        Task<Result<SemanticRevisionSchemaResponse>> GetActiveRevisionSchemaAsync(CancellationToken cancellationToken = default);
        Task<Result<List<SemanticLayerListItemResponse>>> GetSemanticLayersAsync(Guid? layerId = null, CancellationToken cancellationToken = default);
        Task<Result<bool>> DeleteSemanticLayerAsync(Guid layerId, CancellationToken cancellationToken = default);
        Task<Result<bool>> DeleteSourceFileAsync(Guid fileId, CancellationToken cancellationToken = default);
        Task<Result<RetrieveSourceFileResponse>> UpsertSourceFileAsync(Guid layerId, Guid? fileId, UpsertSourceFileRequest request, CancellationToken cancellationToken = default);
        Task<Result<bool>> ToggleTablePermissionAsync(Guid layerId, string tableName, bool isAllowed, CancellationToken cancellationToken = default);
        Task<Result<bool>> ToggleUserTablePermissionAsync(Guid layerId, string email, string tableName, bool isAllowed, CancellationToken cancellationToken = default);
        Task<Result<SemanticLayerTablesResponse>> GetLayerTablesAsync(Guid layerId, CancellationToken cancellationToken = default);
        Task<Result<TablePermissionsResponse>> GetTablePermissionsAsync(Guid layerId, CancellationToken cancellationToken = default);
        Task<Result<bool>> ActivateSemanticLayerAsync(Guid layerId, CancellationToken cancellationToken = default);
    }
}
