using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Auth
{
    public record UserDto(
    string UserId,
    string FirstName,
    string LastName,
    string Email,
    string Role,
    string? BranchId);
}
