using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.DTOs.Users;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using System.Security.Claims;

namespace EnterpriseAiCopilot.Api.Controllers;

[ApiController]
[Route("api/v1/users")]
public sealed class UsersController : ControllerBase
{
    private readonly IApplicationDbContext _context;
    public UsersController(IApplicationDbContext context)
    {
        _context = context;
    }

    [HttpGet("me")]
    [Authorize]
    public async Task<IActionResult> GetCurrentUser(CancellationToken cancellationToken)
    {
        var userIdClaim = User.FindFirstValue(ClaimTypes.NameIdentifier);
        if (!Guid.TryParse(userIdClaim, out var userId))
        {
            return Unauthorized(new
            {
                status = "Failed",
                errorCode = "UNAUTHORIZED",
                message = "User ID claim is missing or invalid."
            });
        }

        var user = await _context.Users
            .AsNoTracking()
            .Where(item => item.Id == userId)
            .Select(item => new PublicUserResponse
            {
                UserId = item.Id.ToString(),
                FirstName = item.FirstName,
                LastName = item.LastName,
                Email = item.Email,
                Role = item.Role,
                BranchId = item.BranchId,
                BranchName = item.Branch == null ? null : item.Branch.BranchName,
                CreatedAt = item.CreatedAt,
                LastModifiedAt = item.LastModifiedAt
            })
            .FirstOrDefaultAsync(cancellationToken);

        if (user is null)
        {
            return NotFound(new
            {
                status = "Failed",
                errorCode = "NOT_FOUND",
                message = "Current user was not found."
            });
        }

        return Ok(user);
    }

    [HttpGet]
    [Authorize(Roles = "admin")]
    public async Task<IActionResult> GetUsers([FromQuery] Guid? id, CancellationToken cancellationToken)
    {
        if (id.HasValue)
        {
            var user = await BuildUserQuery(id.Value)
                .FirstOrDefaultAsync(cancellationToken);

            if (user is null)
            {
                return NotFound(new
                {
                    status = "Failed",
                    errorCode = "NOT_FOUND",
                    message = "User not found."
                });
            }

            return Ok(user);
        }

        var users = await BuildUserQuery()
            .OrderBy(user => user.Email)
            .ToListAsync(cancellationToken);

        return Ok(users);
    }

    private IQueryable<UserDetailsResponse> BuildUserQuery(Guid? userId = null)
    {
        var query = _context.Users.AsNoTracking();
        if (userId.HasValue)
            query = query.Where(user => user.Id == userId.Value);

        return query.Select(user => new UserDetailsResponse
        {
            UserId = user.Id.ToString(),
            FirstName = user.FirstName,
            LastName = user.LastName,
            Email = user.Email,
            Role = user.Role,
            BranchId = user.BranchId,
            BranchName = user.Branch == null ? null : user.Branch.BranchName,
            CreatedAt = user.CreatedAt,
            LastModifiedAt = user.LastModifiedAt,
            ConversationCount = _context.Conversations.Count(conversation => conversation.UserId == user.Id.ToString()),
            QueryCount = _context.CopilotQueryHistories.Count(history => history.UserId == user.Id.ToString()),
            TablePermissions = _context.UserTablePermissions
                .Where(permission => permission.UserId == user.Id)
                .Select(permission => new UserTablePermissionResponse
                {
                    SemanticLayerId = permission.SemanticLayerId.ToString(),
                    TableName = permission.TableName,
                    IsAllowed = permission.IsAllowed
                })
                .ToList()
        });
    }
}
