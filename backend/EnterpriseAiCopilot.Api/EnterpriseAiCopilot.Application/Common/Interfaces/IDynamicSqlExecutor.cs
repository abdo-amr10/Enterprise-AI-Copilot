using EnterpriseAiCopilot.Application.Common.Models;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.Common.Interfaces
{
    public interface IDynamicSqlExecutor
    {
        Task<Result<object>> ExecuteQueryAsync(string sqlQuery, int branchId, CancellationToken cancellationToken = default);
    }
}
