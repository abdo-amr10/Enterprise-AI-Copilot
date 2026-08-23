using EnterpriseAiCopilot.Application.Common.Models;
using EnterpriseAiCopilot.Application.DTOs.Copilot;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.Common.Interfaces
{
    public interface IAiRuntimeClient
    {
        Task<AiRuntimeResponse> ProcessQuestionAsync(AskCopilotRequest request, CancellationToken cancellationToken = default);
    }
}
