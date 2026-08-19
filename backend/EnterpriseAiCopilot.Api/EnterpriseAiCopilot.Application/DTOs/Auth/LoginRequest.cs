using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Auth
{
    public record LoginRequest(
    string Email,
    string Password);
}
