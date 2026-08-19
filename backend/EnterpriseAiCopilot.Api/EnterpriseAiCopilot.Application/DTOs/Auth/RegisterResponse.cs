using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Auth
{
    public record RegisterResponse(
    string Status,
    string Message,
    UserDto User);
}
