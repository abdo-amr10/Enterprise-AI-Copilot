using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.DTOs.SemanticLayer;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace EnterpriseAiCopilot.Api.Controllers
{
    [Route("api/v1/semantic-layer")]
    [ApiController]
    [Authorize(Roles = "admin")]
    public class SemanticLayerController : ControllerBase
    {
        private readonly ISemanticLayerService _semanticLayerService;

        public SemanticLayerController(ISemanticLayerService semanticLayerService)
        {
            _semanticLayerService = semanticLayerService;
        }

        [HttpPost("upload")]
        public async Task<IActionResult> UploadDataSources([FromForm] UploadDataSourcesRequest request, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.UploadDataSourcesAsync(request, cancellationToken);

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

        [HttpPost("generate-draft")]
        public async Task<IActionResult> GenerateDraft([FromBody] GenerateDraftRequest request, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.GenerateDraftAsync(request, cancellationToken);

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

        [HttpPost("review")]
        public async Task<IActionResult> ReviewRevision([FromBody] ReviewRevisionRequest request, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.ReviewRevisionAsync(request, cancellationToken);

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

        [HttpGet("files/{fileId}")]
        public async Task<IActionResult> GetSourceFile(Guid fileId, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.GetSourceFileAsync(fileId, cancellationToken);

            if (!result.IsSuccess)
            {
                return NotFound(new
                {
                    status = "Failed",
                    errorCode = "NOT_FOUND",
                    message = result.ErrorMessage
                });
            }

            return Ok(result.Data);
        }

        [HttpGet("revisions/{revisionId}")]
        public async Task<IActionResult> GetRevision(Guid revisionId, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.GetRevisionAsync(revisionId, cancellationToken);

            if (!result.IsSuccess)
            {
                return NotFound(new
                {
                    status = "Failed",
                    errorCode = "NOT_FOUND",
                    message = result.ErrorMessage
                });
            }

            return Ok(result.Data);
        }

        [HttpPost("revisions/{revisionId}/submit")]
        public async Task<IActionResult> SubmitRevision(Guid revisionId, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.SubmitRevisionAsync(revisionId, cancellationToken);

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

        [HttpGet("status")]
        public async Task<IActionResult> GetStatus(CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.GetSemanticLayerStatusAsync(cancellationToken);

            if (!result.IsSuccess)
            {
                return NotFound(new
                {
                    status = "Failed",
                    errorCode = "NOT_FOUND",
                    message = result.ErrorMessage
                });
            }

            return Ok(result.Data);
        }

        [HttpGet("revisions/active/schema")]
        public async Task<IActionResult> GetActiveRevisionSchema(CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.GetActiveRevisionSchemaAsync(cancellationToken);

            if (!result.IsSuccess)
            {
                return NotFound(new
                {
                    status = "Failed",
                    errorCode = "NOT_FOUND",
                    message = result.ErrorMessage
                });
            }

            return Ok(result.Data);
        }

        [HttpGet]
        public async Task<IActionResult> GetSemanticLayers([FromQuery(Name = "id")] Guid? layerId, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.GetSemanticLayersAsync(layerId, cancellationToken);

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

        [HttpDelete("{layerId}")]
        public async Task<IActionResult> DeleteSemanticLayer(Guid layerId, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.DeleteSemanticLayerAsync(layerId, cancellationToken);

            if (!result.IsSuccess)
            {
                return BadRequest(new
                {
                    status = "Failed",
                    errorCode = "BUSINESS_ERROR",
                    message = result.ErrorMessage
                });
            }

            return Ok(new { Message = "Semantic Layer and all associated files deleted successfully." });
        }

        [HttpDelete("files/{fileId}")]
        public async Task<IActionResult> DeleteSourceFile(Guid fileId, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.DeleteSourceFileAsync(fileId, cancellationToken);

            if (!result.IsSuccess)
            {
                return BadRequest(new
                {
                    status = "Failed",
                    errorCode = "BUSINESS_ERROR",
                    message = result.ErrorMessage
                });
            }

            return Ok(new { Message = "Source file deleted successfully." });
        }

        [HttpPut("{layerId}/files")]
        public async Task<IActionResult> UpsertSourceFile(Guid layerId, [FromQuery] Guid? fileId, [FromForm] UpsertSourceFileRequest request, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.UpsertSourceFileAsync(layerId, fileId, request, cancellationToken);

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
        [HttpPatch("{layerId}/tables/{tableName}/toggle")]
        public async Task<IActionResult> ToggleTableStatus(Guid layerId, string tableName, [FromBody] bool isAllowed, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.ToggleTablePermissionAsync(layerId, tableName, isAllowed, cancellationToken);

            if (!result.IsSuccess)
            {
                return BadRequest(new
                {
                    status = "Failed",
                    errorCode = "BUSINESS_ERROR",
                    message = result.ErrorMessage
                });
            }

            return Ok(new { Message = $"Table '{tableName}' access set to {isAllowed}" });
        }

        [HttpPatch("{layerId}/users/table-permission")]
        public async Task<IActionResult> ToggleUserTableStatus(
            Guid layerId,
            [FromQuery] string email,
            [FromQuery] string tableName,
            [FromBody] bool? isAllowed,
            CancellationToken cancellationToken)
        {
            if (!isAllowed.HasValue)
            {
                return BadRequest(new
                {
                    status = "Failed",
                    errorCode = "VALIDATION_ERROR",
                    message = "The request body must contain a boolean value: true or false."
                });
            }

            var result = await _semanticLayerService.ToggleUserTablePermissionAsync(
                layerId, email, tableName, isAllowed.Value, cancellationToken);

            if (!result.IsSuccess)
            {
                var notFound = result.ErrorMessage?.StartsWith("NOT_FOUND:", StringComparison.OrdinalIgnoreCase) == true;
                return StatusCode(notFound ? StatusCodes.Status404NotFound : StatusCodes.Status400BadRequest, new
                {
                    status = "Failed",
                    errorCode = notFound ? "NOT_FOUND" : "BUSINESS_ERROR",
                    message = result.ErrorMessage
                });
            }

            return Ok(new
            {
                Message = $"Table '{tableName}' access for user '{email}' set to {isAllowed}"
            });
        }


        [HttpPost("{layerId}/activate")]
        public async Task<IActionResult> ActivateSemanticLayer(Guid layerId, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.ActivateSemanticLayerAsync(layerId, cancellationToken);

            if (!result.IsSuccess)
            {
                return BadRequest(new
                {
                    status = "Failed",
                    errorCode = "BUSINESS_ERROR",
                    message = result.ErrorMessage
                });
            }

            return Ok(new { Message = "Semantic Layer activated successfully." });
        }
    }
}
