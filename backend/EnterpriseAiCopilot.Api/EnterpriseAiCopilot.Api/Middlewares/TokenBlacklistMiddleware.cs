using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Caching.Distributed;

namespace EnterpriseAiCopilot.API.Middlewares;

public class TokenBlacklistMiddleware
{
    private readonly RequestDelegate _next;

    public TokenBlacklistMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(HttpContext context, IDistributedCache cache)
    {
        var authHeader = context.Request.Headers.Authorization.ToString();

        if (!string.IsNullOrEmpty(authHeader) && authHeader.StartsWith("Bearer "))
        {
            var token = authHeader.Substring("Bearer ".Length).Trim();

            var isRevoked = await cache.GetStringAsync($"blacklist_{token}");

            if (!string.IsNullOrEmpty(isRevoked))
            {
                context.Response.StatusCode = StatusCodes.Status401Unauthorized;
                context.Response.ContentType = "application/json";
                await context.Response.WriteAsync("{\"message\": \"Token has been revoked. Please log in again.\"}");
                return;
            }
        }

        await _next(context);
    }
}