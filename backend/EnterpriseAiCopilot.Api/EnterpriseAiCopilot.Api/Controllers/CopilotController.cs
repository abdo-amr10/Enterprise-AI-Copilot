using System.Security.Claims;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.DTOs.Copilot;

namespace EnterpriseAiCopilot.Api.Controllers
{
    [Authorize]
    [ApiController]
    [Route("api/v1/copilot")]
    public class CopilotController : ControllerBase
    {
        private readonly ICopilotService _copilotService;

        public CopilotController(ICopilotService copilotService)
        {
            _copilotService = copilotService;
        }

        [HttpPost("ask")]
        public async Task<IActionResult> AskQuestion([FromBody] AskCopilotRequest request, CancellationToken cancellationToken)
        {
            var userId = User.FindFirstValue(ClaimTypes.NameIdentifier);
            if (string.IsNullOrWhiteSpace(userId))
            {
                return Unauthorized("User ID claim is missing.");
            }

            var branchId = User.FindFirstValue("branchId");
            if (string.IsNullOrWhiteSpace(branchId))
            {
                return BadRequest("Branch ID claim is missing or invalid.");
            }

            var result = await _copilotService.AskQuestionAsync(request, userId, branchId, cancellationToken);
            if (!result.IsSuccess)
            {
                return BadRequest(result);
            }

            return Ok(result);
        }

        [HttpGet("history")]
        public async Task<IActionResult> GetUserHistory(CancellationToken cancellationToken)
        {
            var userId = User.FindFirstValue(ClaimTypes.NameIdentifier);
            if (string.IsNullOrWhiteSpace(userId))
            {
                return Unauthorized("User ID claim is missing.");
            }

            var branchId = User.FindFirstValue("branchId");
            if (string.IsNullOrWhiteSpace(branchId))
            {
                return BadRequest("Branch ID claim is missing or invalid.");
            }

            var result = await _copilotService.GetUserHistoryAsync(userId, branchId, cancellationToken);
            if (!result.IsSuccess)
            {
                return BadRequest(result);
            }

            return Ok(result);
        }

        [HttpGet("history/{queryId}")]
        public async Task<IActionResult> GetQueryDetails(string queryId, CancellationToken cancellationToken)
        {
            var userId = User.FindFirstValue(ClaimTypes.NameIdentifier);
            if (string.IsNullOrWhiteSpace(userId))
            {
                return Unauthorized("User ID claim is missing.");
            }

            var branchId = User.FindFirstValue("branchId");
            if (string.IsNullOrWhiteSpace(branchId))
            {
                return BadRequest("Branch ID claim is missing or invalid.");
            }

            var result = await _copilotService.GetQueryDetailsAsync(queryId, userId, branchId, cancellationToken);
            if (!result.IsSuccess)
            {
                return NotFound(result);
            }

            return Ok(result);
        }
    }
}
