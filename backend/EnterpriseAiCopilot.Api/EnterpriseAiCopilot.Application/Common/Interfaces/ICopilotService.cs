using System.Threading;
using System.Threading.Tasks;
using EnterpriseAiCopilot.Application.Common.Models;
using EnterpriseAiCopilot.Application.DTOs.Copilot;

namespace EnterpriseAiCopilot.Application.Common.Interfaces
{
    public interface ICopilotService
    {
        Task<Result<AskCopilotResponse>> AskQuestionAsync(AskCopilotRequest request, string userId, string branchId, CancellationToken cancellationToken = default);

        Task<Result<QueryHistoryResponse>> GetUserHistoryAsync(string userId, string branchId, CancellationToken cancellationToken = default);

        Task<Result<QueryDetailsResponse>> GetQueryDetailsAsync(string queryId, string userId, string branchId, CancellationToken cancellationToken = default);
    }
}
