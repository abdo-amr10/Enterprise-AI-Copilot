using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Auth
{
    public record LoginResponse(
    string Status,
    string Token,
    DateTime ExpiresAt);
}
