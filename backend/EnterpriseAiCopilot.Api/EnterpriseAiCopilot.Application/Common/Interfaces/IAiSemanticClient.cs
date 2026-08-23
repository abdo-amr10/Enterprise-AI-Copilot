using EnterpriseAiCopilot.Application.DTOs.SemanticLayer;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.Common.Interfaces
{
    public interface IAiSemanticClient
    {
        Task<AiSemanticDraftResult> GenerateDraftAsync(GenerateDraftRequest request, CancellationToken cancellationToken = default);
        Task<AiSemanticBaseResult> ReviewDraftAsync(string revisionId, string decision, string? comments, CancellationToken cancellationToken = default);
        Task<AiSemanticBaseResult> ValidateDraftAsync(string revisionId, CancellationToken cancellationToken = default);
    }
}
