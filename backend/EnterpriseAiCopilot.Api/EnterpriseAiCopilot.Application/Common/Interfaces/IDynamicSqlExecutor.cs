using EnterpriseAiCopilot.Application.Common.Models;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.Common.Interfaces
{
    public interface IDynamicSqlExecutor
    {
        Task<Result<object>> ExecuteQueryAsync(string sqlQuery, string branchId, Guid semanticLayerId, Guid userId, CancellationToken cancellationToken = default);
    }
}
