using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.DTOs.Auth;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace EnterpriseAiCopilot.API.Controllers;

[ApiController]
[Route("api/v1/[controller]")]
public class AuthController : ControllerBase
{
    private readonly IAuthService _authService;
    private readonly ICurrentUserService _currentUserService;

    public AuthController(IAuthService authService, ICurrentUserService currentUserService)
    {
        _authService = authService;
        _currentUserService = currentUserService;
    }

    [HttpPost("login")]
    [AllowAnonymous]
    public async Task<IActionResult> Login([FromBody] LoginRequest request, CancellationToken cancellationToken)
    {
        var result = await _authService.LoginAsync(request, cancellationToken);

        if (!result.IsSuccess)
        {
            return Unauthorized(new { Message = result.ErrorMessage });
        }

        return Ok(result.Data);
    }

    [HttpPost("register")]
    [Authorize(Roles = "admin")]
    public async Task<IActionResult> Register([FromBody] RegisterRequest request, CancellationToken cancellationToken)
    {
        var currentAdminId = _currentUserService.UserId;

        var result = await _authService.RegisterAsync(request, currentAdminId!, cancellationToken);

        if (!result.IsSuccess)
        {
            return BadRequest(new { Message = result.ErrorMessage });
        }

        return Ok(result.Data);
    }

    [HttpPost("admin/change-password")]
    [Authorize(Roles = "admin")]
    public async Task<IActionResult> AdminChangePassword([FromBody] AdminChangePasswordRequest request, CancellationToken cancellationToken)
    {
        var result = await _authService.AdminChangePasswordAsync(request, cancellationToken);

        if (!result.IsSuccess)
        {
            return NotFound(new { Message = result.ErrorMessage });
        }

        return Ok(new { Message = result.Data });
    }

    [HttpDelete("delete-user")]
    [Authorize(Roles = "admin")]
    public async Task<IActionResult> DeleteUser([FromQuery] DeleteUserRequest request, CancellationToken cancellationToken)
    {
        var result = await _authService.DeleteUserAsync(request.Email, cancellationToken);

        if (!result.IsSuccess)
        {
            return NotFound(new { Message = result.ErrorMessage });
        }

        return Ok(new { Message = "User deleted successfully." });
    }

    [HttpPost("logout")]
    [Authorize]
    public async Task<IActionResult> Logout(CancellationToken cancellationToken)
    {
        var token = Request.Headers.Authorization.ToString().Replace("Bearer ", "").Trim();

        var result = await _authService.LogoutAsync(token, cancellationToken);

        if (!result.IsSuccess) return BadRequest(new { Message = result.ErrorMessage });

        return Ok(result.Data);
    }

    [HttpPut("admin/update-role")]
    [Authorize(Roles = "admin")]
    public async Task<IActionResult> UpdateUserRole([FromBody] UpdateUserRoleRequest request, CancellationToken cancellationToken)
    {
        var result = await _authService.UpdateUserRoleAsync(request.Email, request.NewRole, cancellationToken);

        if (!result.IsSuccess)
        {
            return BadRequest(new { Message = result.ErrorMessage });
        }

        return Ok(new { Message = result.Data });
    }
}