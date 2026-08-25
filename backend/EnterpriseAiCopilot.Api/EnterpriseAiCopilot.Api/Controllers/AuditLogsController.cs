using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.DTOs.Audit;

namespace EnterpriseAiCopilot.Api.Controllers
{
    [Route("api/v1/audit-logs")]
    [ApiController]
    [Authorize(Roles = "admin")]
    public class AuditLogsController : ControllerBase
    {
        private readonly IAuditService _auditService;

        public AuditLogsController(IAuditService auditService)
        {
            _auditService = auditService;
        }

        [HttpGet]
        public async Task<IActionResult> GetAuditLogs([FromQuery] AuditLogQuery query, CancellationToken cancellationToken)
        {
            var result = await _auditService.GetAuditLogsAsync(query, cancellationToken);

            if (!result.IsSuccess)
            {
                return BadRequest(new
                {
                    status = "Failed",
                    errorCode = "BUSINESS_ERROR",
                    message = result.ErrorMessage
                });
            }

            return Ok(result.Data);
        }
    }
}