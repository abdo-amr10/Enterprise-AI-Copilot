using BCrypt.Net;
using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.Common.Models;
using EnterpriseAiCopilot.Application.DTOs.Auth;
using EnterpriseAiCopilot.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using EnterpriseAiCopilot.Domain.Constants;
using Microsoft.Extensions.Caching.Distributed;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Configuration;
using Microsoft.IdentityModel.Tokens;
using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;

namespace EnterpriseAiCopilot.Infrastructure.Identity.Services
{
    public class AuthService : IAuthService
    {
        private readonly IApplicationDbContext _context;
        private readonly IConfiguration _config;
        private readonly IDistributedCache _cache;
        private readonly IAuditService _auditService; 

        public AuthService(IApplicationDbContext context, IConfiguration config, IDistributedCache cache, IAuditService auditService)
        {
            _context = context;
            _config = config;
            _cache = cache;
            _auditService = auditService;
        }

        public async Task<Result<RegisterResponse>> RegisterAsync(RegisterRequest request, string currentAdminId, CancellationToken cancellationToken = default)
        {
            var normalizedEmail = request.Email.Trim().ToLower();

            if (await _context.Users.AnyAsync(u => u.Email == normalizedEmail, cancellationToken))
            {
                return Result<RegisterResponse>.Failure("Email is already registered.");
            }

            var user = new User
            {
                FirstName = request.FirstName,
                LastName = request.LastName,
                Email = normalizedEmail, 
                PasswordHash = BCrypt.Net.BCrypt.HashPassword(request.Password),
                Role = request.Role.ToLower(),
                BranchId = request.BranchId,
                CreatedBy = currentAdminId
            };

            _context.Users.Add(user);
            await _context.SaveChangesAsync(cancellationToken);

            var userDto = new UserDto(
                UserId: $"USR-{user.Id}",
                FirstName: user.FirstName,
                LastName: user.LastName,
                Email: user.Email,
                Role: user.Role,
                BranchId: user.BranchId
            );

            var response = new RegisterResponse(
                Status: "Success",
                Message: "User registered successfully.",
                User: userDto
            );

            await _auditService.LogEventAsync(
                action: AuditActions.UserRegistration,
                userId: currentAdminId,
                status: "Success",
                resourceId: $"NewUser:{user.Id}",
                cancellationToken: cancellationToken
            );

            return Result<RegisterResponse>.Success(response);
        }

        public async Task<Result<LoginResponse>> LoginAsync(LoginRequest request, CancellationToken cancellationToken = default)
        {
            var normalizedEmail = request.Email.Trim().ToLower();

            var user = await _context.Users.FirstOrDefaultAsync(u => u.Email == normalizedEmail, cancellationToken);

            if (user == null || !BCrypt.Net.BCrypt.Verify(request.Password, user.PasswordHash))
            {
                return Result<LoginResponse>.Failure("Invalid email or password.");
            }

            var claims = new List<Claim>
            {
                new Claim(ClaimTypes.NameIdentifier, user.Id.ToString()),
                new Claim(ClaimTypes.Email, user.Email),
                new Claim(ClaimTypes.Role, user.Role.ToLower())
            };

            if (!string.IsNullOrEmpty(user.BranchId))
            {
                claims.Add(new Claim("branchId", user.BranchId));
            }

            var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(_config["JwtSettings:Secret"]!));
            var creds = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);
            var expiresAt = DateTime.UtcNow.AddMinutes(60);

            var token = new JwtSecurityToken(
                issuer: _config["JwtSettings:Issuer"],
                audience: _config["JwtSettings:Audience"],
                claims: claims,
                expires: expiresAt,
                signingCredentials: creds
            );

            var tokenString = new JwtSecurityTokenHandler().WriteToken(token);

            var response = new LoginResponse(
                Status: "Success",
                Token: tokenString,
                ExpiresAt: expiresAt
            );

            await _auditService.LogEventAsync(
                action: AuditActions.UserLogin,
                userId: user.Id.ToString(),
                status: "Success",
                cancellationToken: cancellationToken
            );

            return Result<LoginResponse>.Success(response);
        }

        public async Task<Result<string>> AdminChangePasswordAsync(AdminChangePasswordRequest request, CancellationToken cancellationToken = default)
        {
            var normalizedEmail = request.Email.Trim().ToLower();

            var user = await _context.Users.FirstOrDefaultAsync(u => u.Email == normalizedEmail, cancellationToken);

            if (user == null)
            {
                return Result<string>.Failure("User not found.");
            }

            user.PasswordHash = BCrypt.Net.BCrypt.HashPassword(request.NewPassword);
            await _context.SaveChangesAsync(cancellationToken);

            return Result<string>.Success("User password has been updated successfully.");
        }

        public async Task<Result<bool>> DeleteUserAsync(string email, CancellationToken cancellationToken = default)
        {
            var normalizedEmail = email.Trim().ToLower();

            var user = await _context.Users.FirstOrDefaultAsync(u => u.Email == normalizedEmail, cancellationToken);

            if (user == null)
            {
                return Result<bool>.Failure("User not found.");
            }

            _context.Users.Remove(user);
            await _context.SaveChangesAsync(cancellationToken);

            return Result<bool>.Success(true);
        }

        public async Task<Result<LogoutResponse>> LogoutAsync(string token, CancellationToken cancellationToken = default)
        {
            var handler = new JwtSecurityTokenHandler();

            if (handler.CanReadToken(token))
            {
                var jwtToken = handler.ReadJwtToken(token);
                var expiry = jwtToken.ValidTo;
                var timeRemaining = expiry - DateTime.UtcNow;

                if (timeRemaining > TimeSpan.Zero)
                {
                    var options = new DistributedCacheEntryOptions
                    {
                        AbsoluteExpirationRelativeToNow = timeRemaining
                    };

                    await _cache.SetStringAsync($"blacklist_{token}", "revoked", options, cancellationToken);
                }
            }

            var response = new LogoutResponse("Success", "Logged out successfully.");
            return Result<LogoutResponse>.Success(response);
        }

        public async Task<Result<string>> UpdateUserRoleAsync(string email, string newRole, CancellationToken cancellationToken = default)
        {
            var normalizedEmail = email.Trim().ToLower();
            newRole = newRole.Trim().ToLower();

            var user = await _context.Users
                .FirstOrDefaultAsync(u => u.Email == normalizedEmail, cancellationToken);

            if (user == null)
            {
                return Result<string>.Failure("User not found.");
            }

            user.Role = newRole;

            await _context.SaveChangesAsync(cancellationToken);

            return Result<string>.Success("User role has been updated successfully.");
        }
    }
}