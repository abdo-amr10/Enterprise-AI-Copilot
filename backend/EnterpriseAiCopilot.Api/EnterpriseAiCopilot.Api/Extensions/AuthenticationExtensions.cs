using EnterpriseAiCopilot.Application.Common.Interfaces;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Caching.Distributed;
using Microsoft.IdentityModel.Tokens;
using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;

namespace EnterpriseAiCopilot.Api.Extensions
{
    public static class AuthenticationExtensions
    {
        public static IServiceCollection AddJwtAuthentication(this IServiceCollection services, IConfiguration configuration)
        {
            var secretKey = configuration["JwtSettings:Secret"] ?? "EnterpriseAiCopilot_SecretKey_2026_SecureKey!";
            var key = Encoding.UTF8.GetBytes(secretKey);

            services.AddAuthentication(options =>
            {
                options.DefaultAuthenticateScheme = JwtBearerDefaults.AuthenticationScheme;
                options.DefaultChallengeScheme = JwtBearerDefaults.AuthenticationScheme;
            })
            .AddJwtBearer(options =>
            {
                options.TokenValidationParameters = new TokenValidationParameters
                {
                    ValidateIssuer = true,
                    ValidateAudience = true,
                    ValidateLifetime = true,
                    ValidateIssuerSigningKey = true,
                    ValidIssuer = configuration["JwtSettings:Issuer"] ?? "EnterpriseAiCopilot",
                    ValidAudience = configuration["JwtSettings:Audience"] ?? "EnterpriseAiCopilotUsers",
                    IssuerSigningKey = new SymmetricSecurityKey(key)
                };

                options.Events = new JwtBearerEvents
                {
                    OnTokenValidated = async context =>
                    {
                        var cache = context.HttpContext.RequestServices.GetRequiredService<IDistributedCache>();
                        var dbContext = context.HttpContext.RequestServices.GetRequiredService<IApplicationDbContext>();

                        var userIdStr = context.Principal?.FindFirstValue(ClaimTypes.NameIdentifier);
                        var jti = context.Principal?.FindFirstValue(JwtRegisteredClaimNames.Jti);
                        var iatStr = context.Principal?.FindFirstValue(JwtRegisteredClaimNames.Iat);
                        var currentRole = context.Principal?.FindFirstValue(ClaimTypes.Role);

                        if (string.IsNullOrEmpty(userIdStr)) return;

                        if (!string.IsNullOrEmpty(jti) && await cache.GetStringAsync($"blacklist_jti_{jti}") != null)
                        {
                            context.Fail("Unauthorized: Token has been revoked.");
                            return;
                        }

                        var userRevokeTimeStr = await cache.GetStringAsync($"revoke_user_{userIdStr}");
                        if (!string.IsNullOrEmpty(userRevokeTimeStr) && !string.IsNullOrEmpty(iatStr))
                        {
                            if (long.TryParse(userRevokeTimeStr, out long revokeTime) && long.TryParse(iatStr, out long iat))
                            {
                                if (iat <= revokeTime)
                                {
                                    context.Fail("Unauthorized: User session has been invalidated.");
                                    return;
                                }
                            }
                        }

                        if (Guid.TryParse(userIdStr, out Guid userId))
                        {
                            var user = await dbContext.Users.AsNoTracking().FirstOrDefaultAsync(u => u.Id == userId);
                            if (user == null || !user.Role.Equals(currentRole, StringComparison.OrdinalIgnoreCase))
                            {
                                context.Fail("Unauthorized: User no longer exists or role has changed.");
                                return;
                            }
                        }
                    },
                    OnChallenge = async context =>
                    {
                        context.HandleResponse();
                        context.Response.StatusCode = StatusCodes.Status401Unauthorized;
                        context.Response.ContentType = "application/json";

                        var errorMessage = context.AuthenticateFailure?.Message ?? "Unauthorized: Invalid or expired token.";
                        var response = new { success = false, message = errorMessage };
                        await context.Response.WriteAsJsonAsync(response);
                    },
                    OnForbidden = async context =>
                    {
                        context.Response.StatusCode = StatusCodes.Status403Forbidden;
                        context.Response.ContentType = "application/json";

                        var response = new { success = false, message = "Forbidden: You do not have permission to access this resource." };
                        await context.Response.WriteAsJsonAsync(response);
                    }
                };
            });

            return services;
        }
    }
}