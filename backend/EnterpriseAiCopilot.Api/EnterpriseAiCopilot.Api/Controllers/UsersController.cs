using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.DTOs.Users;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace EnterpriseAiCopilot.Api.Controllers;

[ApiController]
[Route("api/v1/users")]
[Authorize(Roles = "admin")]
public sealed class UsersController : ControllerBase
{
    private readonly IApplicationDbContext _context;

    public UsersController(IApplicationDbContext context)
    {
        _context = context;
    }

    [HttpGet]
    public async Task<IActionResult> GetUsers([FromQuery] Guid? id, CancellationToken cancellationToken)
    {
        if (id.HasValue)
        {
            var user = await BuildUserQuery(id.Value).FirstOrDefaultAsync(cancellationToken);
            if (user is null)
            {
                return NotFound(new { status = "Failed", errorCode = "NOT_FOUND", message = "User not found." });
            }
            return Ok(user);
        }

        var users = await BuildUserQuery().OrderBy(user => user.Email).ToListAsync(cancellationToken);
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
