using EnterpriseAiCopilot.Application.DTOs.Copilot;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.Common.Interfaces
{
    public interface IAiResultFormatterClient
    {
        Task<CopilotReport> FormatExecutionResultAsync(
            string question,
            object executionResult,
            CancellationToken cancellationToken = default);
    }
}
