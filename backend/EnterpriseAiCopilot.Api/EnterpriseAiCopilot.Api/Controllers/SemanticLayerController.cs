using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.DTOs.SemanticLayer;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace EnterpriseAiCopilot.Api.Controllers
{
    [Route("api/v1/semantic-layer")]
    [ApiController]
    [Authorize]
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
                return BadRequest(new { Message = result.ErrorMessage });
            }

            return Ok(result.Data);
        }

        [HttpPost("generate-draft")]
        public async Task<IActionResult> GenerateDraft([FromBody] GenerateDraftRequest request, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.GenerateDraftAsync(request, cancellationToken);

            if (!result.IsSuccess)
            {
                return BadRequest(new { Message = result.ErrorMessage });
            }

            return Ok(result.Data);
        }

        [HttpPost("review")]
        public async Task<IActionResult> ReviewRevision([FromBody] ReviewRevisionRequest request, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.ReviewRevisionAsync(request, cancellationToken);
            if (!result.IsSuccess) return BadRequest(new { Message = result.ErrorMessage });
            return Ok(result.Data);
        }

        [HttpGet("files/{fileId}")]
        public async Task<IActionResult> GetSourceFile(Guid fileId, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.GetSourceFileAsync(fileId, cancellationToken);
            if (!result.IsSuccess) return NotFound(new { Message = result.ErrorMessage });
            return Ok(result.Data);
        }

        [HttpGet("revisions/{revisionId}")]
        public async Task<IActionResult> GetRevision(Guid revisionId, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.GetRevisionAsync(revisionId, cancellationToken);

            if (!result.IsSuccess)
            {
                return NotFound(new { Message = result.ErrorMessage });
            }

            return Ok(result.Data);
        }

        [HttpPost("revisions/{revisionId}/submit")]
        public async Task<IActionResult> SubmitRevision(Guid revisionId, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.SubmitRevisionAsync(revisionId, cancellationToken);

            if (!result.IsSuccess)
            {
                return BadRequest(new { Message = result.ErrorMessage });
            }

            return Ok(result.Data);
        }

        [HttpGet("status")]
        public async Task<IActionResult> GetStatus(CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.GetSemanticLayerStatusAsync(cancellationToken);

            if (!result.IsSuccess)
            {
                return NotFound(new { Message = result.ErrorMessage });
            }

            return Ok(result.Data);
        }

        [HttpDelete("{layerId}")]
        public async Task<IActionResult> DeleteSemanticLayer(Guid layerId, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.DeleteSemanticLayerAsync(layerId, cancellationToken);

            if (!result.IsSuccess)
            {
                return BadRequest(new { Message = result.ErrorMessage });
            }

            return Ok(new { Message = "Semantic Layer and all associated files deleted successfully." });
        }

        [HttpDelete("files/{fileId}")]
        public async Task<IActionResult> DeleteSourceFile(Guid fileId, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.DeleteSourceFileAsync(fileId, cancellationToken);

            if (!result.IsSuccess)
            {
                return BadRequest(new { Message = result.ErrorMessage });
            }

            return Ok(new { Message = "Source file deleted successfully." });
        }

        [HttpPut("{layerId}/files")]
        public async Task<IActionResult> UpsertSourceFile(Guid layerId, [FromQuery] Guid? fileId, [FromForm] UpsertSourceFileRequest request, CancellationToken cancellationToken)
        {
            var result = await _semanticLayerService.UpsertSourceFileAsync(layerId, fileId, request, cancellationToken);

            if (!result.IsSuccess)
            {
                return BadRequest(new { Message = result.ErrorMessage });
            }

            return Ok(result.Data);
        }
    }
}
