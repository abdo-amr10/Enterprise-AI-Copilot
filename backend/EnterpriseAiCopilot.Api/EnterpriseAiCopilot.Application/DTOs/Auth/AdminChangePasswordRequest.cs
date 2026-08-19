using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Auth
{
    public record AdminChangePasswordRequest(
    string Email,
    string NewPassword,
    string ConfirmPassword);
}
