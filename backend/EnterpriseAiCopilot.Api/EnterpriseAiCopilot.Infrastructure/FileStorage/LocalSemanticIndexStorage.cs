using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.Common.Models;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using System.Collections.Concurrent;
using System.IO.Compression;

namespace EnterpriseAiCopilot.Infrastructure.FileStorage;

public sealed class LocalSemanticIndexStorage : ISemanticIndexStorage
{
    private const string FaissFileName = "semantic_index.faiss";
    private const string IndexMetadataFileName = "index_metadata.json";
    private const string DocumentMetadataFileName = "document_metadata.json";
    private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> RevisionLocks = new();
    private readonly string _baseStoragePath;
    private readonly string[] _readStoragePaths;
    private readonly ILogger<LocalSemanticIndexStorage> _logger;

    public LocalSemanticIndexStorage(IConfiguration configuration, IHostEnvironment environment, ILogger<LocalSemanticIndexStorage> logger)
    {
        _logger = logger;
        var configuredRoot = configuration["FileStorage:BasePath"];
        var storageRoot = string.IsNullOrWhiteSpace(configuredRoot) ? Path.Combine(environment.ContentRootPath, "Storage") : configuredRoot;
        _baseStoragePath = Path.GetFullPath(storageRoot).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        _readStoragePaths = new[] { _baseStoragePath, Path.Combine(environment.ContentRootPath, "Storage"), Path.Combine(AppContext.BaseDirectory, "Storage") }
            .Select(Path.GetFullPath).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        Directory.CreateDirectory(_baseStoragePath);
    }

    public async Task<Result<bool>> SaveArtifactBundleAsync(Guid layerId, Guid revisionId, Stream faissStream, string indexMetadataJson, string documentMetadataJson, CancellationToken cancellationToken = default)
    {
        var gate = RevisionLocks.GetOrAdd(revisionId, _ => new SemaphoreSlim(1, 1));
        if (!await gate.WaitAsync(0, cancellationToken)) return Result<bool>.Failure("CONCURRENT_OPERATION: Upload for this revision is already in progress.");
        string? staging = null;
        try
        {
            var layerFolder = Path.Combine("SemanticIndexes", $"Layer_{layerId}");
            var target = ResolveContained(Path.Combine(layerFolder, $"Revision_{revisionId}"), _baseStoragePath);
            if (Directory.Exists(target)) return Result<bool>.Failure("ALREADY_EXISTS: Artifact already exists for this revision.");
            staging = ResolveContained(Path.Combine(layerFolder, $".staging_{revisionId}_{Guid.NewGuid():N}"), _baseStoragePath);
            Directory.CreateDirectory(staging);
            await using (var output = new FileStream(Path.Combine(staging, FaissFileName), FileMode.CreateNew, FileAccess.Write, FileShare.None))
                await faissStream.CopyToAsync(output, cancellationToken);
            await File.WriteAllTextAsync(Path.Combine(staging, IndexMetadataFileName), indexMetadataJson, cancellationToken);
            await File.WriteAllTextAsync(Path.Combine(staging, DocumentMetadataFileName), documentMetadataJson, cancellationToken);
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            Directory.Move(staging, target);
            staging = null;
            return Result<bool>.Success(true);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to save semantic index artifact for revision {RevisionId}", revisionId);
            return Result<bool>.Failure($"Storage failure: {ex.Message}");
        }
        finally
        {
            if (staging is not null && Directory.Exists(staging)) try { Directory.Delete(staging, true); } catch { }
            gate.Release();
        }
    }

    public async Task<Result<byte[]>> GetArtifactBundleZipAsync(Guid layerId, Guid revisionId, CancellationToken cancellationToken = default)
    {
        var relative = Path.Combine("SemanticIndexes", $"Layer_{layerId}", $"Revision_{revisionId}");
        var directory = _readStoragePaths.Select(root => ResolveContained(relative, root)).FirstOrDefault(path => Directory.Exists(path) && IsValidBundle(path));
        if (directory is null) return Result<byte[]>.Failure("ARTIFACT_NOT_FOUND: Semantic index artifact not found for this revision.");
        await using var memory = new MemoryStream();
        using (var archive = new ZipArchive(memory, ZipArchiveMode.Create, true))
        {
            foreach (var file in new[] { FaissFileName, IndexMetadataFileName, DocumentMetadataFileName })
            {
                cancellationToken.ThrowIfCancellationRequested();
                var entry = archive.CreateEntry(file, CompressionLevel.Fastest);
                await using var input = File.OpenRead(Path.Combine(directory, file));
                await using var output = entry.Open();
                await input.CopyToAsync(output, cancellationToken);
            }
        }
        return Result<byte[]>.Success(memory.ToArray());
    }

    public Task<bool> ArtifactExistsAsync(Guid layerId, Guid revisionId, CancellationToken cancellationToken = default)
    {
        var relative = Path.Combine("SemanticIndexes", $"Layer_{layerId}", $"Revision_{revisionId}");
        return Task.FromResult(_readStoragePaths.Select(root => ResolveContained(relative, root)).Any(path => Directory.Exists(path) && IsValidBundle(path)));
    }

    public Task<Result<bool>> DeleteRevisionArtifactAsync(Guid layerId, Guid revisionId, CancellationToken cancellationToken = default)
        => DeleteDirectoryAsync(Path.Combine("SemanticIndexes", $"Layer_{layerId}", $"Revision_{revisionId}"), "revision artifact");

    public Task<Result<bool>> DeleteLayerArtifactsAsync(Guid layerId, CancellationToken cancellationToken = default)
        => DeleteDirectoryAsync(Path.Combine("SemanticIndexes", $"Layer_{layerId}"), "layer artifacts");

    private Task<Result<bool>> DeleteDirectoryAsync(string relative, string label)
    {
        try
        {
            var path = ResolveContained(relative, _baseStoragePath);
            if (Directory.Exists(path)) Directory.Delete(path, true);
            return Task.FromResult(Result<bool>.Success(true));
        }
        catch (Exception ex) { return Task.FromResult(Result<bool>.Failure($"Failed to delete {label}: {ex.Message}")); }
    }

    private static bool IsValidBundle(string path) => new[] { FaissFileName, IndexMetadataFileName, DocumentMetadataFileName }.All(file => new FileInfo(Path.Combine(path, file)) is { Exists: true, Length: > 0 });
    private static string ResolveContained(string relative, string root)
    {
        var full = Path.GetFullPath(Path.Combine(root, relative));
        var prefix = root.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        if (!full.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Storage path escapes storage root.");
        return full;
    }
}
