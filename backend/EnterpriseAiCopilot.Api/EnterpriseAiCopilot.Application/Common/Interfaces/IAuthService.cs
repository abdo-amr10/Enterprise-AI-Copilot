using EnterpriseAiCopilot.Application.Common.Models;
using EnterpriseAiCopilot.Application.DTOs.Auth;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.Common.Interfaces
{
    public interface IAuthService
    {
        Task<Result<RegisterResponse>> RegisterAsync(RegisterRequest request, string currentAdminId, CancellationToken cancellationToken = default);
        Task<Result<LoginResponse>> LoginAsync(LoginRequest request, CancellationToken cancellationToken = default);
        Task<Result<string>> AdminChangePasswordAsync(AdminChangePasswordRequest request, CancellationToken cancellationToken = default);
        Task<Result<bool>> DeleteUserAsync(string email, CancellationToken cancellationToken = default);
        Task<Result<LogoutResponse>> LogoutAsync(string token, CancellationToken cancellationToken = default);
        Task<Result<string>> UpdateUserRoleAsync(string email, string newRole, CancellationToken cancellationToken = default);
    }
}
