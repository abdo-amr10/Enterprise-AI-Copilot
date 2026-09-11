using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using System.Text.Json;

namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer;

public class UploadIndexArtifactRequest
{
    [FromForm(Name = "faissIndex")]
    public IFormFile? FaissIndex { get; set; }

    [FromForm(Name = "indexMetadata")]
    public string? IndexMetadata { get; set; }

    [FromForm(Name = "indexMetadataFile")]
    public IFormFile? IndexMetadataFile { get; set; }

    [FromForm(Name = "documentMetadata")]
    public string? DocumentMetadata { get; set; }

    [FromForm(Name = "documentMetadataFile")]
    public IFormFile? DocumentMetadataFile { get; set; }

    public async Task<string?> ReadIndexMetadataJsonAsync(CancellationToken cancellationToken = default)
        => await ReadValueAsync(IndexMetadata, IndexMetadataFile, cancellationToken);

    public async Task<string?> ReadDocumentMetadataJsonAsync(CancellationToken cancellationToken = default)
        => await ReadValueAsync(DocumentMetadata, DocumentMetadataFile, cancellationToken);

    private static async Task<string?> ReadValueAsync(string? value, IFormFile? file, CancellationToken cancellationToken)
    {
        if (!string.IsNullOrWhiteSpace(value)) return value.Trim();
        if (file is null || file.Length == 0) return null;
        using var reader = new StreamReader(file.OpenReadStream());
        return (await reader.ReadToEndAsync(cancellationToken)).Trim();
    }
}

public sealed class SemanticIndexMetadataDto
{
    public string? RevisionId { get; set; }
    public string? SemanticLayerId { get; set; }
    public int? EmbeddingDimension { get; set; }
    public int? DocumentCount { get; set; }
    public string? SemanticContentHash { get; set; }
}

public sealed class UploadIndexArtifactResponse
{
    public string SemanticLayerId { get; set; } = string.Empty;
    public string RevisionId { get; set; } = string.Empty;
    public string Status { get; set; } = "READY";
    public bool ArtifactReady { get; set; } = true;
    public string UpdatedAt { get; set; } = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
}
