using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.Common.Interfaces
{
    public interface ICurrentUserService 
    {
        string? UserId { get; }
        string? Email { get; }
        string? Role { get; }
        string? BranchId { get; }
    }
}
