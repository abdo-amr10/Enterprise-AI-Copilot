using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Copilot
{
    public class QueryHistoryResponse
    {
        public List<QueryHistoryItemResponse> Items { get; set; } = new();
    }
}
