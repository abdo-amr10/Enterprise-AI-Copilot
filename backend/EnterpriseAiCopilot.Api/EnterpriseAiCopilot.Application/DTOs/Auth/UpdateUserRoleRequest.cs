using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Auth
{
    public record UpdateUserRoleRequest(
    string Email,
    string NewRole
);
}
