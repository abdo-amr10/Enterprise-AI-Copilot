using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.Common.Models;
using EnterpriseAiCopilot.Application.DTOs;
using EnterpriseAiCopilot.Application.DTOs.SemanticLayer;
using EnterpriseAiCopilot.Domain.Constants;
using EnterpriseAiCopilot.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Logging;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace EnterpriseAiCopilot.Application.Services
{
    public class SemanticLayerService : ISemanticLayerService
    {
        private readonly IApplicationDbContext _context;
        private readonly IFileStorage _fileStorage;
        private readonly ICurrentUserService _currentUserService;
        private readonly IAiSemanticClient _aiSemanticClient;
        private readonly IMemoryCache _cache;
        private readonly ILogger<SemanticLayerService> _logger;
        private readonly IAuditService _auditService;

        public SemanticLayerService(
            IApplicationDbContext context,
            IFileStorage fileStorage,
            ICurrentUserService currentUserService,
            IAiSemanticClient aiSemanticClient,
            IMemoryCache cache,
            ILogger<SemanticLayerService> logger,
            IAuditService auditService)
        {
            _context = context;
            _fileStorage = fileStorage;
            _currentUserService = currentUserService;
            _aiSemanticClient = aiSemanticClient;
            _cache = cache;
            _logger = logger;
            _auditService = auditService;
        }

        private static string AllowedTablesCacheKey(Guid layerId) => $"AllowedTables_{layerId}";

        public async Task<Result<UploadDataSourcesResponse>> UploadDataSourcesAsync(UploadDataSourcesRequest request, CancellationToken cancellationToken = default)
        {
            if (request.SchemaFile == null || request.SchemaFile.Length == 0)
                return Result<UploadDataSourcesResponse>.Failure("Schema file is strictly required and cannot be empty.");

            if (request.SchemaFile.FileName.EndsWith(".pdf", StringComparison.OrdinalIgnoreCase))
                return Result<UploadDataSourcesResponse>.Failure("PDF files cannot be used as a database schema. Please upload a JSON or SQL file.");

            var currentUser = _currentUserService.UserId ?? "SYSTEM";

            var semanticLayer = new SemanticLayer
            {
                Name = request.Name,
                DatabaseName = request.Name,
                Description = request.Description,
                IsActive = false
            };

            _context.SemanticLayers.Add(semanticLayer);
            await _context.SaveChangesAsync(cancellationToken);

            var folderName = $"SemanticSources/Layer_{semanticLayer.Id}";

            var schemaResult = await _fileStorage.SaveFileAsync(request.SchemaFile, folderName, cancellationToken);
            if (!schemaResult.IsSuccess) return Result<UploadDataSourcesResponse>.Failure($"Schema file upload failed: {schemaResult.ErrorMessage}");

            var schemaFile = new SemanticSourceFile
            {
                FileName = request.SchemaFile.FileName,
                FileType = "schema",
                FileSize = request.SchemaFile.Length,
                StoragePath = schemaResult.Data!,
                UploadedBy = currentUser,
                SemanticLayerId = semanticLayer.Id
            };
            _context.SemanticSourceFiles.Add(schemaFile);

            SemanticSourceFile? docFile = null;
            if (request.DocumentationFile != null && request.DocumentationFile.Length > 0)
            {
                var docResult = await _fileStorage.SaveFileAsync(request.DocumentationFile, folderName, cancellationToken);
                if (!docResult.IsSuccess) return Result<UploadDataSourcesResponse>.Failure($"Documentation upload failed: {docResult.ErrorMessage}");

                docFile = new SemanticSourceFile
                {
                    FileName = request.DocumentationFile.FileName,
                    FileType = "documentation",
                    FileSize = request.DocumentationFile.Length,
                    StoragePath = docResult.Data!,
                    UploadedBy = currentUser,
                    SemanticLayerId = semanticLayer.Id
                };
                _context.SemanticSourceFiles.Add(docFile);
            }

            SemanticSourceFile? glossaryFile = null;
            if (request.GlossaryFile != null && request.GlossaryFile.Length > 0)
            {
                var glossaryResult = await _fileStorage.SaveFileAsync(request.GlossaryFile, folderName, cancellationToken);
                if (!glossaryResult.IsSuccess) return Result<UploadDataSourcesResponse>.Failure($"Glossary upload failed: {glossaryResult.ErrorMessage}");

                glossaryFile = new SemanticSourceFile
                {
                    FileName = request.GlossaryFile.FileName,
                    FileType = "glossary",
                    FileSize = request.GlossaryFile.Length,
                    StoragePath = glossaryResult.Data!,
                    UploadedBy = currentUser,
                    SemanticLayerId = semanticLayer.Id
                };
                _context.SemanticSourceFiles.Add(glossaryFile);
            }

            SemanticSourceFile? sampleDataFile = null;
            if (request.SampleDataFile != null && request.SampleDataFile.Length > 0)
            {
                var sampleResult = await _fileStorage.SaveFileAsync(request.SampleDataFile, folderName, cancellationToken);
                if (!sampleResult.IsSuccess) return Result<UploadDataSourcesResponse>.Failure($"Sample data upload failed: {sampleResult.ErrorMessage}");

                sampleDataFile = new SemanticSourceFile
                {
                    FileName = request.SampleDataFile.FileName,
                    FileType = "sampledata",
                    FileSize = request.SampleDataFile.Length,
                    StoragePath = sampleResult.Data!,
                    UploadedBy = currentUser,
                    SemanticLayerId = semanticLayer.Id
                };
                _context.SemanticSourceFiles.Add(sampleDataFile);
            }

            if (schemaResult.IsSuccess && schemaResult.Data != null)
            {
                var fileContentResult = await _fileStorage.GetFileAsync(schemaResult.Data, cancellationToken);
                if (fileContentResult.IsSuccess && fileContentResult.Data != null)
                {
                    string contentStr = System.Text.Encoding.UTF8.GetString(fileContentResult.Data);
                    var extractionResult = await ExtractAndSaveTablesFromSchemaAsync(contentStr, semanticLayer.Id, cancellationToken);
                    if (!extractionResult.IsSuccess)
                    {
                        return Result<UploadDataSourcesResponse>.Failure(extractionResult.ErrorMessage ?? "Failed to extract tables.");
                    }
                }
            }

            await _context.SaveChangesAsync(cancellationToken);

            _cache.Remove(AllowedTablesCacheKey(semanticLayer.Id));

            var response = new UploadDataSourcesResponse
            {
                Status = "SourcesLoaded",
                Message = "Sources loaded successfully.",
                SemanticLayerId = semanticLayer.Id.ToString(),
                Name = semanticLayer.Name,
                Description = semanticLayer.Description,
                Sources = new SemanticSources
                {
                    SchemaFileId = schemaFile.Id.ToString(),
                    DocumentationFileId = docFile?.Id.ToString(),
                    GlossaryFileId = glossaryFile?.Id.ToString(),
                    SampleDataFileId = sampleDataFile?.Id.ToString()
                },
                HasDocumentation = docFile != null,
                HasGlossary = glossaryFile != null,
                HasSampleData = sampleDataFile != null
            };

            await _auditService.LogEventAsync(
                action: AuditActions.SemanticLayerUpload,
                userId: currentUser,
                status: "Success",
                resourceId: semanticLayer.Id.ToString(),
                cancellationToken: cancellationToken
            );

            return Result<UploadDataSourcesResponse>.Success(response);
        }

        public async Task<Result<GenerateDraftResponse>> GenerateDraftAsync(GenerateDraftRequest request, CancellationToken cancellationToken = default)
        {
            if (!Guid.TryParse(request.SemanticLayerId, out Guid layerId))
                return Result<GenerateDraftResponse>.Failure("Invalid SemanticLayerId format.");

            var semanticLayer = await _context.SemanticLayers
                .Include(s => s.Revisions)
                .Include(s => s.SourceFiles)
                .FirstOrDefaultAsync(s => s.Id == layerId, cancellationToken);

            if (semanticLayer == null)
                return Result<GenerateDraftResponse>.Failure("Semantic Layer not found.");

            var aiDraftResult = await _aiSemanticClient.GenerateDraftAsync(request, cancellationToken);
            if (!aiDraftResult.IsSuccess)
                return Result<GenerateDraftResponse>.Failure($"AI_RUNTIME_ERROR: Failed to generate draft. {aiDraftResult.ErrorMessage}");

            string generatedJson = aiDraftResult.ContentJson ?? "{}";
            string? physicalSchemaJson = null;
            var schemaSource = semanticLayer.SourceFiles
                .Where(file => file.FileType.Equals("schema", StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(file => file.CreatedAt)
                .FirstOrDefault();
            if (schemaSource != null)
            {
                var schemaFileResult = await _fileStorage.GetFileAsync(schemaSource.StoragePath, cancellationToken);
                if (schemaFileResult.IsSuccess && schemaFileResult.Data != null)
                {
                    physicalSchemaJson = System.Text.Encoding.UTF8.GetString(schemaFileResult.Data);
                }
            }

            int objectsCount = aiDraftResult.RegeneratedObjectsCount > 0
                                ? aiDraftResult.RegeneratedObjectsCount
                                : (request.TriggerType == "FullRebuild" ? 15 : (request.AffectedObjects?.Count ?? 0));

            int nextVersion = semanticLayer.Revisions.Any() ? semanticLayer.Revisions.Max(r => r.VersionNumber) + 1 : 1;

            var newRevisionId = Guid.NewGuid();
            var revision = new SemanticRevision
            {
                Id = newRevisionId,
                VersionNumber = nextVersion,
                ContentJson = generatedJson,
                PhysicalSchemaJson = physicalSchemaJson,
                Status = "PendingReview",
                SemanticLayerId = semanticLayer.Id,
                RegenerationType = request.TriggerType,
                RegeneratedObjectsCount = objectsCount
            };

            _context.SemanticRevisions.Add(revision);
            await _context.SaveChangesAsync(cancellationToken);

            var response = new GenerateDraftResponse
            {
                Status = "DraftGenerated",
                SemanticLayerId = request.SemanticLayerId,
                RevisionId = newRevisionId.ToString(),
                RegeneratedObjectsCount = objectsCount,
                BuildTimestamp = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                LastRegenerationType = request.TriggerType
            };

            if (request.TriggerType == "Incremental")
            {
                response.BaseRevisionId = request.BaseRevisionId;
                response.AffectedObjects = request.AffectedObjects;
            }

            return Result<GenerateDraftResponse>.Success(response);
        }

        public async Task<Result<ReviewRevisionResponse>> ReviewRevisionAsync(ReviewRevisionRequest request, CancellationToken cancellationToken = default)
        {
            if (!Guid.TryParse(request.SemanticLayerId, out Guid layerId) || !Guid.TryParse(request.RevisionId, out Guid revId))
                return Result<ReviewRevisionResponse>.Failure("Invalid Id format.");

            var validDecisions = new[] { "Approve", "Reject" };
            if (!validDecisions.Contains(request.Decision, StringComparer.OrdinalIgnoreCase))
                return Result<ReviewRevisionResponse>.Failure("Invalid decision. Allowed values are 'Approve' or 'Reject'.");

            var revision = await _context.SemanticRevisions
                .FirstOrDefaultAsync(r => r.Id == revId && r.SemanticLayerId == layerId, cancellationToken);

            if (revision == null)
                return Result<ReviewRevisionResponse>.Failure("Revision not found.");

            if (revision.Status.Equals("Approved", StringComparison.OrdinalIgnoreCase))
                return Result<ReviewRevisionResponse>.Failure("This revision is already approved.");

            if (request.Decision.Equals("Approve", StringComparison.OrdinalIgnoreCase))
            {
                if (!string.IsNullOrEmpty(revision.ContentJson))
                {
                    try
                    {
                        using var doc = JsonDocument.Parse(revision.ContentJson);
                        if (doc.RootElement.TryGetProperty("validation_issues", out var issues) ||
                            doc.RootElement.TryGetProperty("validationIssues", out issues))
                        {
                            if (issues.ValueKind == JsonValueKind.Array && issues.GetArrayLength() > 0)
                            {
                                foreach (var issue in issues.EnumerateArray())
                                {
                                    if (issue.TryGetProperty("severity", out var sev) &&
                                        sev.GetString()?.Equals("error", StringComparison.OrdinalIgnoreCase) == true)
                                    {
                                        return Result<ReviewRevisionResponse>.Failure("Cannot approve revision with unresolved validation errors.");
                                    }
                                    if (issue.TryGetProperty("category", out var cat) &&
                                        cat.GetString()?.Equals("security_domain", StringComparison.OrdinalIgnoreCase) == true)
                                    {
                                        return Result<ReviewRevisionResponse>.Failure("Cannot approve revision with unresolved security validation issues.");
                                    }
                                }
                            }
                        }
                    }
                    catch
                    {
                    }
                }
            }

            var aiReviewResult = await _aiSemanticClient.ReviewDraftAsync(request.RevisionId, request.Decision, request.Comments, cancellationToken);
            if (!aiReviewResult.IsSuccess)
                return Result<ReviewRevisionResponse>.Failure($"AI_RUNTIME_ERROR: Failed to submit review to AI. {aiReviewResult.ErrorMessage}");

            var currentUser = _currentUserService.UserId ?? "SYSTEM";
            var timeNow = DateTime.UtcNow;

            revision.Status = request.Decision.Equals("Approve", StringComparison.OrdinalIgnoreCase) ? "Approved" : "Rejected";
            revision.ReviewNotes = request.Comments;
            revision.ReviewedBy = currentUser;
            revision.ReviewedAt = timeNow;

            var response = new ReviewRevisionResponse
            {
                SemanticLayerId = request.SemanticLayerId,
                RevisionId = request.RevisionId,
                Status = revision.Status
            };

            if (revision.Status == "Approved")
            {
                // Approval validates the revision only. Activation is an
                // explicit operation handled by ActivateSemanticLayerAsync.
                response.Version = $"v{revision.VersionNumber}.0";
                response.ApprovedBy = currentUser;
                response.ApprovedAt = timeNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
            }
            else
            {
                response.Comments = request.Comments;
                response.RejectedBy = currentUser;
                response.RejectedAt = timeNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
            }

            try
            {
                await _context.SaveChangesAsync(cancellationToken);
            }
            catch (DbUpdateException ex)
            {
                _logger.LogWarning(ex, "Revision {RevisionId} could not be reviewed because the active layer changed concurrently.", revision.Id);
                return Result<ReviewRevisionResponse>.Failure("The active semantic layer changed concurrently. Please retry.");
            }

            if (revision.Status == "Approved")
            {
                _cache.Remove(AllowedTablesCacheKey(layerId));
            }

            var actionToLog = revision.Status == "Approved" ? AuditActions.SemanticLayerApproval : AuditActions.SemanticLayerRejection;

            await _auditService.LogEventAsync(
                action: actionToLog,
                userId: currentUser,
                status: "Success",
                resourceId: revision.Id.ToString(),
                cancellationToken: cancellationToken
            );

            return Result<ReviewRevisionResponse>.Success(response);
        }

        public async Task<Result<RetrieveSourceFileResponse>> GetSourceFileAsync(Guid fileId, CancellationToken cancellationToken = default)
        {
            var sourceFile = await _context.SemanticSourceFiles
                .FirstOrDefaultAsync(f => f.Id == fileId, cancellationToken);

            if (sourceFile == null)
                return Result<RetrieveSourceFileResponse>.Failure("File not found.");

            var fileResult = await _fileStorage.GetFileAsync(sourceFile.StoragePath, cancellationToken);
            if (!fileResult.IsSuccess)
                return Result<RetrieveSourceFileResponse>.Failure($"Failed to read file from storage: {fileResult.ErrorMessage}");

            if (fileResult.Data == null || fileResult.Data.Length == 0)
                return Result<RetrieveSourceFileResponse>.Failure("File content is empty or corrupted.");

            string fileContentStr;

            if (sourceFile.FileName.EndsWith(".pdf", StringComparison.OrdinalIgnoreCase))
            {
                try
                {
                    using var pdfDocument = UglyToad.PdfPig.PdfDocument.Open(fileResult.Data);
                    var textBuilder = new System.Text.StringBuilder();
                    foreach (var page in pdfDocument.GetPages())
                    {
                        textBuilder.Append(page.Text);
                        textBuilder.Append(" ");
                    }
                    fileContentStr = textBuilder.ToString();
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Failed to parse PDF file {FileId}", fileId);
                    return Result<RetrieveSourceFileResponse>.Failure("Failed to parse PDF content.");
                }
            }
            else
            {
                fileContentStr = System.Text.Encoding.UTF8.GetString(fileResult.Data);
            }

            object finalContent = fileContentStr;

            if (sourceFile.FileName.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
            {
                try
                {
                    finalContent = JsonSerializer.Deserialize<object>(fileContentStr) ?? fileContentStr;
                }
                catch
                {
                }
            }

            var response = new RetrieveSourceFileResponse
            {
                Status = "Success",
                FileId = sourceFile.Id.ToString(),
                FileType = sourceFile.FileType,
                FileName = sourceFile.FileName,
                Content = finalContent
            };

            return Result<RetrieveSourceFileResponse>.Success(response);
        }

        public async Task<Result<RetrieveSemanticRevisionResponse>> GetRevisionAsync(Guid revisionId, CancellationToken cancellationToken = default)
        {
            var revision = await _context.SemanticRevisions
                .FirstOrDefaultAsync(r => r.Id == revisionId, cancellationToken);

            if (revision == null)
                return Result<RetrieveSemanticRevisionResponse>.Failure("Revision not found.");

            var parsedContent = new SemanticRevisionContent();
            if (!string.IsNullOrEmpty(revision.ContentJson))
            {
                try
                {
                    parsedContent = JsonSerializer.Deserialize<SemanticRevisionContent>(
                        revision.ContentJson,
                        new JsonSerializerOptions { PropertyNameCaseInsensitive = true }
                    ) ?? new SemanticRevisionContent();
                }
                catch
                {
                }
            }

            var response = new RetrieveSemanticRevisionResponse
            {
                SemanticLayerId = revision.SemanticLayerId.ToString(),
                RevisionId = revision.Id.ToString(),
                Status = revision.Status,
                Version = revision.Status == "PendingReview" ? "draft" : $"v{revision.VersionNumber}.0",
                BuildTimestamp = revision.CreatedAt.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                LastRegenerationType = string.IsNullOrEmpty(revision.RegenerationType) ? "Unknown" : revision.RegenerationType,
                Content = parsedContent,
                CreatedAt = revision.CreatedAt.ToString("yyyy-MM-ddTHH:mm:ssZ")
            };

            return Result<RetrieveSemanticRevisionResponse>.Success(response);
        }

        public async Task<Result<SubmitRevisionResponse>> SubmitRevisionAsync(Guid revisionId, CancellationToken cancellationToken = default)
        {
            var revision = await _context.SemanticRevisions
                .FirstOrDefaultAsync(r => r.Id == revisionId, cancellationToken);

            if (revision == null)
                return Result<SubmitRevisionResponse>.Failure("Revision not found.");

            var aiValidationResult = await _aiSemanticClient.ValidateDraftAsync(revisionId.ToString(), cancellationToken);
            if (!aiValidationResult.IsSuccess)
                return Result<SubmitRevisionResponse>.Failure($"VALIDATION_FAILED: AI Runtime rejected the draft. {aiValidationResult.ErrorMessage}");

            revision.Status = "Submitted";

            await _context.SaveChangesAsync(cancellationToken);

            var response = new SubmitRevisionResponse
            {
                Status = "Submitted",
                SemanticLayerId = revision.SemanticLayerId.ToString(),
                RevisionId = revision.Id.ToString(),
                Message = "Revision submitted and validated successfully by AI Runtime."
            };

            return Result<SubmitRevisionResponse>.Success(response);
        }

        public async Task<Result<SemanticLayerStatusResponse>> GetSemanticLayerStatusAsync(CancellationToken cancellationToken = default)
        {
            var semanticLayer = await _context.SemanticLayers
                .Include(s => s.Revisions)
                .Include(s => s.SourceFiles)
                .SingleOrDefaultAsync(s => s.IsActive, cancellationToken);

            if (semanticLayer == null)
                return Result<SemanticLayerStatusResponse>.Failure("No active Semantic Layer found.");

            var approvedRevision = semanticLayer.Revisions
                .Where(r => r.Status == "Approved")
                .OrderByDescending(r => r.VersionNumber)
                .FirstOrDefault();

            if (approvedRevision == null)
            {
                var latestRevision = semanticLayer.Revisions
                    .OrderByDescending(r => r.VersionNumber)
                    .FirstOrDefault();

                if (latestRevision == null)
                    return Result<SemanticLayerStatusResponse>.Failure("No revisions found for the current Semantic Layer.");

                return Result<SemanticLayerStatusResponse>.Success(new SemanticLayerStatusResponse
                {
                    SemanticLayerId = semanticLayer.Id.ToString(),
                    Status = "PendingReview",
                    Version = "draft",
                    RevisionId = latestRevision.Id.ToString(),
                    BuildTimestamp = latestRevision.CreatedAt.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                    LastRegenerationType = string.IsNullOrEmpty(latestRevision.RegenerationType) ? "Unknown" : latestRevision.RegenerationType,
                    Sources = BuildSemanticSources(semanticLayer.SourceFiles)
                });
            }

            var response = new SemanticLayerStatusResponse
            {
                SemanticLayerId = semanticLayer.Id.ToString(),
                Status = approvedRevision.Status,
                Version = $"v{approvedRevision.VersionNumber}.0",
                RevisionId = approvedRevision.Id.ToString(),
                BuildTimestamp = approvedRevision.CreatedAt.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                LastRegenerationType = string.IsNullOrEmpty(approvedRevision.RegenerationType) ? "Unknown" : approvedRevision.RegenerationType,
                Sources = BuildSemanticSources(semanticLayer.SourceFiles)
            };

            return Result<SemanticLayerStatusResponse>.Success(response);
        }

        public async Task<Result<List<SemanticLayerListItemResponse>>> GetSemanticLayersAsync(Guid? layerId = null, CancellationToken cancellationToken = default)
        {
            var query = _context.SemanticLayers
                .AsNoTracking()
                .AsQueryable();

            if (layerId.HasValue)
            {
                query = query.Where(layer => layer.Id == layerId.Value);
            }

            var layers = await query
                .OrderByDescending(layer => layer.IsActive)
                .ThenBy(layer => layer.Name)
                .Select(layer => new SemanticLayerListItemResponse
                {
                    SemanticLayerId = layer.Id.ToString(),
                    Name = layer.Name,
                    DatabaseName = layer.DatabaseName,
                    Description = layer.Description,
                    IsActive = layer.IsActive,
                    HasApprovedRevision = layer.Revisions.Any(revision => revision.Status == "Approved")
                })
                .ToListAsync(cancellationToken);

            return Result<List<SemanticLayerListItemResponse>>.Success(layers);
        }

        public async Task<Result<SemanticRevisionSchemaResponse>> GetActiveRevisionSchemaAsync(CancellationToken cancellationToken = default)
        {
            var activeRevision = await _context.SemanticRevisions
                .AsNoTracking()
                .Where(revision => revision.SemanticLayer != null && revision.SemanticLayer.IsActive && revision.Status == "Approved")
                .OrderByDescending(revision => revision.VersionNumber)
                .FirstOrDefaultAsync(cancellationToken);

            if (activeRevision == null)
                return Result<SemanticRevisionSchemaResponse>.Failure("No approved active semantic revision found.");

            if (string.IsNullOrWhiteSpace(activeRevision.PhysicalSchemaJson))
            {
                // Backward-compatible bridge for revisions created before the
                // physical schema snapshot column existed. New revisions use
                // the database snapshot above and never need this file read.
                var schemaFile = await _context.SemanticSourceFiles
                    .AsNoTracking()
                    .Where(file => file.SemanticLayerId == activeRevision.SemanticLayerId &&
                                   file.FileType == "schema")
                    .OrderByDescending(file => file.CreatedAt)
                    .FirstOrDefaultAsync(cancellationToken);

                if (schemaFile == null)
                    return Result<SemanticRevisionSchemaResponse>.Failure("The active revision has no physical schema snapshot or schema source file.");

                var legacyFile = await _fileStorage.GetFileAsync(schemaFile.StoragePath, cancellationToken);
                if (!legacyFile.IsSuccess || legacyFile.Data == null)
                    return Result<SemanticRevisionSchemaResponse>.Failure($"The active revision schema source could not be read: {legacyFile.ErrorMessage}");

                activeRevision.PhysicalSchemaJson = System.Text.Encoding.UTF8.GetString(legacyFile.Data);
            }

            try
            {
                using var document = JsonDocument.Parse(activeRevision.PhysicalSchemaJson);
                return Result<SemanticRevisionSchemaResponse>.Success(new SemanticRevisionSchemaResponse
                {
                    SemanticLayerId = activeRevision.SemanticLayerId.ToString(),
                    RevisionId = activeRevision.Id.ToString(),
                    Status = activeRevision.Status,
                    Schema = document.RootElement.Clone()
                });
            }
            catch (JsonException ex)
            {
                _logger.LogError(ex, "Physical schema snapshot is invalid for revision {RevisionId}", activeRevision.Id);
                return Result<SemanticRevisionSchemaResponse>.Failure("The active revision contains an invalid physical schema snapshot.");
            }
        }

        private static SemanticSources BuildSemanticSources(IEnumerable<SemanticSourceFile> sourceFiles)
        {
            var files = sourceFiles.OrderBy(f => f.CreatedAt).ToList();

            var schemaFile = files.FirstOrDefault(IsSchemaFile)
                ?? files.FirstOrDefault(IsSchemaFallbackFile);

            var documentationFile = files.FirstOrDefault(IsDocumentationFile);
            var glossaryFile = files.FirstOrDefault(IsGlossaryFile);
            var sampleDataFile = files.FirstOrDefault(IsSampleDataFile);

            return new SemanticSources
            {
                SchemaFileId = schemaFile?.Id.ToString(),
                DocumentationFileId = documentationFile?.Id.ToString(),
                GlossaryFileId = glossaryFile?.Id.ToString(),
                SampleDataFileId = sampleDataFile?.Id.ToString()
            };
        }

        private static SemanticSourceFile? FindSourceFileBySemanticType(IEnumerable<SemanticSourceFile> sourceFiles, string fileType)
        {
            var files = sourceFiles.OrderBy(f => f.CreatedAt).ToList();

            return fileType.ToLowerInvariant() switch
            {
                "schema" => files.FirstOrDefault(IsSchemaFile)
                    ?? files.FirstOrDefault(IsSchemaFallbackFile),
                "documentation" => files.FirstOrDefault(IsDocumentationFile),
                "glossary" => files.FirstOrDefault(IsGlossaryFile),
                "sampledata" => files.FirstOrDefault(IsSampleDataFile),
                _ => files.FirstOrDefault(f => f.FileType.Equals(fileType, StringComparison.OrdinalIgnoreCase))
            };
        }

        private static string InferSemanticFileType(string fileName)
        {
            if (fileName.Contains("schema", StringComparison.OrdinalIgnoreCase))
                return "schema";

            if (fileName.Contains("documentation", StringComparison.OrdinalIgnoreCase)
                || fileName.Contains("docs", StringComparison.OrdinalIgnoreCase))
                return "documentation";

            if (fileName.Contains("glossary", StringComparison.OrdinalIgnoreCase))
                return "glossary";

            if (fileName.Contains("sample", StringComparison.OrdinalIgnoreCase))
                return "sampledata";

            return Path.GetExtension(fileName).TrimStart('.');
        }

        private static bool IsSchemaFile(SemanticSourceFile file)
        {
            return HasType(file, "schema")
                || (NameContains(file, "schema") && IsSchemaCompatibleExtension(file));
        }

        private static bool IsSchemaFallbackFile(SemanticSourceFile file)
        {
            return IsSchemaCompatibleExtension(file)
                && !IsDocumentationFile(file)
                && !IsGlossaryFile(file)
                && !IsSampleDataFile(file);
        }

        private static bool IsDocumentationFile(SemanticSourceFile file)
        {
            return HasType(file, "documentation")
                || NameContains(file, "documentation")
                || NameContains(file, "docs");
        }

        private static bool IsGlossaryFile(SemanticSourceFile file)
        {
            return HasType(file, "glossary")
                || NameContains(file, "glossary");
        }

        private static bool IsSampleDataFile(SemanticSourceFile file)
        {
            return HasType(file, "sampledata")
                || HasType(file, "sample")
                || NameContains(file, "sample");
        }

        private static bool IsSchemaCompatibleExtension(SemanticSourceFile file)
        {
            return HasType(file, "json")
                || HasType(file, "sql")
                || file.FileName.EndsWith(".json", StringComparison.OrdinalIgnoreCase)
                || file.FileName.EndsWith(".sql", StringComparison.OrdinalIgnoreCase);
        }

        private static bool HasType(SemanticSourceFile file, string value)
        {
            return file.FileType.Equals(value, StringComparison.OrdinalIgnoreCase);
        }

        private static bool NameContains(SemanticSourceFile file, string value)
        {
            return file.FileName.Contains(value, StringComparison.OrdinalIgnoreCase);
        }

        public async Task<Result<bool>> DeleteSemanticLayerAsync(Guid layerId, CancellationToken cancellationToken = default)
        {
            var semanticLayer = await _context.SemanticLayers
                .Include(s => s.SourceFiles)
                .FirstOrDefaultAsync(s => s.Id == layerId, cancellationToken);

            if (semanticLayer == null)
                return Result<bool>.Failure("Semantic Layer not found.");

            var filesToDelete = semanticLayer.SourceFiles?.Select(f => f.StoragePath).ToList() ?? new List<string>();

            try
            {
                _context.SemanticLayers.Remove(semanticLayer);
                await _context.SaveChangesAsync(cancellationToken);
            }
            catch (DbUpdateException ex)
            {
                _logger.LogWarning(ex, "Semantic layer {LayerId} could not be deleted from the database.", layerId);
                return Result<bool>.Failure("Semantic Layer cannot be deleted because it is still referenced by existing records.");
            }

            foreach (var path in filesToDelete)
            {
                var deleteResult = await _fileStorage.DeleteFileAsync(path, cancellationToken);
                if (!deleteResult.IsSuccess)
                {
                    _logger.LogWarning("Physical source file cleanup failed for {StoragePath} after layer {LayerId} deletion.", path, layerId);
                }
            }

            _cache.Remove(AllowedTablesCacheKey(layerId));

            return Result<bool>.Success(true);
        }

        public async Task<Result<bool>> DeleteSourceFileAsync(Guid fileId, CancellationToken cancellationToken = default)
        {
            var sourceFile = await _context.SemanticSourceFiles
                .FirstOrDefaultAsync(f => f.Id == fileId, cancellationToken);

            if (sourceFile == null)
                return Result<bool>.Failure("File not found.");

            var storagePath = sourceFile.StoragePath;

            try
            {
                _context.SemanticSourceFiles.Remove(sourceFile);
                await _context.SaveChangesAsync(cancellationToken);
            }
            catch (DbUpdateException ex)
            {
                _logger.LogWarning(ex, "Source file {FileId} could not be deleted from the database.", fileId);
                return Result<bool>.Failure("The source file could not be deleted from the database.");
            }

            var deleteResult = await _fileStorage.DeleteFileAsync(storagePath, cancellationToken);
            if (!deleteResult.IsSuccess)
            {
                _logger.LogWarning("Physical source file cleanup failed for {StoragePath} after database deletion.", storagePath);
            }

            return Result<bool>.Success(true);
        }

        public async Task<Result<RetrieveSourceFileResponse>> UpsertSourceFileAsync(Guid layerId, Guid? fileId, UpsertSourceFileRequest request, CancellationToken cancellationToken = default)
        {
            var allowedTypes = new[] { "schema", "documentation", "glossary", "sampledata" };
            var fileTypeParam = request.FileType?.ToLower();

            if (!string.IsNullOrEmpty(fileTypeParam) && !allowedTypes.Contains(fileTypeParam, StringComparer.OrdinalIgnoreCase))
            {
                return Result<RetrieveSourceFileResponse>.Failure($"Invalid fileType. Allowed values are: schema, documentation, glossary, sampledata.");
            }

            if (request.File == null || request.File.Length == 0)
                return Result<RetrieveSourceFileResponse>.Failure("File is required and cannot be empty.");

            var isSchema = fileTypeParam == "schema" || (!string.IsNullOrEmpty(request.File.FileName) && request.File.FileName.Contains("schema", StringComparison.OrdinalIgnoreCase));
            if (isSchema && request.File.FileName.EndsWith(".pdf", StringComparison.OrdinalIgnoreCase))
            {
                return Result<RetrieveSourceFileResponse>.Failure("PDF files cannot be used as a database schema. Please upload a JSON or SQL file.");
            }

            var semanticLayer = await _context.SemanticLayers
                .Include(s => s.SourceFiles)
                .FirstOrDefaultAsync(s => s.Id == layerId, cancellationToken);

            if (semanticLayer == null)
                return Result<RetrieveSourceFileResponse>.Failure("Semantic Layer not found.");

            SemanticSourceFile? targetFile = null;

            if (fileId.HasValue && fileId.Value != Guid.Empty)
            {
                targetFile = semanticLayer.SourceFiles.FirstOrDefault(f => f.Id == fileId.Value);
            }
            else if (!string.IsNullOrEmpty(fileTypeParam))
            {
                targetFile = FindSourceFileBySemanticType(semanticLayer.SourceFiles, fileTypeParam);
            }

            var folderName = $"SemanticSources/Layer_{semanticLayer.Id}";
            var currentUser = _currentUserService.UserId ?? "SYSTEM";
            var targetFileTypeForDb = !string.IsNullOrEmpty(fileTypeParam)
                ? fileTypeParam
                : InferSemanticFileType(request.File.FileName);
            var oldStoragePath = targetFile?.StoragePath;

            HashSet<string>? extractedTableNames = null;
            if (isSchema)
            {
                await using var schemaStream = request.File.OpenReadStream();
                using var reader = new StreamReader(schemaStream, leaveOpen: false);
                var schemaContent = await reader.ReadToEndAsync(cancellationToken);
                var extractionResult = ExtractTableNamesFromSchema(schemaContent);

                if (!extractionResult.IsSuccess || extractionResult.Data == null)
                    return Result<RetrieveSourceFileResponse>.Failure(
                        extractionResult.ErrorMessage ?? "Failed to extract tables from the updated schema.");

                extractedTableNames = extractionResult.Data;
            }

            var uploadResult = await _fileStorage.SaveFileAsync(request.File, folderName, cancellationToken);
            if (!uploadResult.IsSuccess)
                return Result<RetrieveSourceFileResponse>.Failure($"Failed to upload file: {uploadResult.ErrorMessage}");

            if (targetFile != null)
            {
                targetFile.FileName = request.File.FileName;
                targetFile.FileType = targetFileTypeForDb;
                targetFile.FileSize = request.File.Length;
                targetFile.StoragePath = uploadResult.Data!;
                targetFile.UploadedBy = currentUser;
            }
            else
            {
                targetFile = new SemanticSourceFile
                {
                    FileName = request.File.FileName,
                    FileType = targetFileTypeForDb,
                    FileSize = request.File.Length,
                    StoragePath = uploadResult.Data!,
                    UploadedBy = currentUser,
                    SemanticLayerId = semanticLayer.Id
                };

                _context.SemanticSourceFiles.Add(targetFile);
            }

            if (extractedTableNames != null)
            {
                var existingTables = await _context.AllowedTables
                    .Where(t => t.SemanticLayerId == semanticLayer.Id)
                    .ToListAsync(cancellationToken);

                _context.AllowedTables.RemoveRange(existingTables);
                foreach (var tableName in extractedTableNames)
                {
                    _context.AllowedTables.Add(new AllowedTable
                    {
                        TableName = tableName,
                        IsAllowed = true,
                        SemanticLayerId = semanticLayer.Id
                    });
                }
            }

            try
            {
                await _context.SaveChangesAsync(cancellationToken);
            }
            catch
            {
                await _fileStorage.DeleteFileAsync(targetFile.StoragePath, cancellationToken);
                throw;
            }

            if (!string.IsNullOrWhiteSpace(oldStoragePath))
            {
                var deleteOldResult = await _fileStorage.DeleteFileAsync(oldStoragePath, cancellationToken);
                if (!deleteOldResult.IsSuccess)
                {
                    _logger.LogWarning("The old source file {StoragePath} could not be deleted after replacement.", oldStoragePath);
                }
            }

            if (extractedTableNames != null)
                _cache.Remove(AllowedTablesCacheKey(semanticLayer.Id));

            var response = new RetrieveSourceFileResponse
            {
                Status = "Success",
                FileId = targetFile.Id.ToString(),
                FileType = targetFile.FileType,
                FileName = targetFile.FileName,
                Content = "File processed and saved successfully."
            };

            return Result<RetrieveSourceFileResponse>.Success(response);
        }

        private async Task<Result<bool>> ExtractAndSaveTablesFromSchemaAsync(string schemaContent, Guid layerId, CancellationToken cancellationToken)
        {
            var extractionResult = ExtractTableNamesFromSchema(schemaContent);
            if (!extractionResult.IsSuccess || extractionResult.Data == null)
                return Result<bool>.Failure(extractionResult.ErrorMessage ?? "No tables could be extracted from the supplied schema.");

            var tableNames = extractionResult.Data;

            var existingTables = await _context.AllowedTables.Where(t => t.SemanticLayerId == layerId).ToListAsync(cancellationToken);
            if (existingTables.Any())
            {
                _context.AllowedTables.RemoveRange(existingTables);
            }

            foreach (var tableName in tableNames)
            {
                _context.AllowedTables.Add(new AllowedTable { TableName = tableName, IsAllowed = true, SemanticLayerId = layerId });
            }

            await _context.SaveChangesAsync(cancellationToken);
            return Result<bool>.Success(true);
        }

        private static Result<HashSet<string>> ExtractTableNamesFromSchema(string schemaContent)
        {
            if (string.IsNullOrWhiteSpace(schemaContent))
                return Result<HashSet<string>>.Failure("Schema content cannot be empty.");

            var tableNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

            try
            {
                using var document = JsonDocument.Parse(schemaContent);
                var root = document.RootElement;

                if (root.ValueKind == JsonValueKind.Object &&
                    root.TryGetProperty("tables", out var tables))
                {
                    if (tables.ValueKind == JsonValueKind.Object)
                    {
                        foreach (var table in tables.EnumerateObject())
                        {
                            if (!string.IsNullOrWhiteSpace(table.Name))
                                tableNames.Add(table.Name.Trim());
                        }
                    }
                    else if (tables.ValueKind == JsonValueKind.Array)
                    {
                        foreach (var table in tables.EnumerateArray())
                        {
                            if (table.ValueKind == JsonValueKind.String)
                            {
                                var name = table.GetString();
                                if (!string.IsNullOrWhiteSpace(name))
                                    tableNames.Add(name.Trim());
                            }
                            else if (table.ValueKind == JsonValueKind.Object &&
                                     table.TryGetProperty("name", out var nameProperty) &&
                                     nameProperty.ValueKind == JsonValueKind.String)
                            {
                                var name = nameProperty.GetString();
                                if (!string.IsNullOrWhiteSpace(name))
                                    tableNames.Add(name.Trim());
                            }
                        }
                    }
                }
            }
            catch (JsonException)
            {
                var regex = new Regex(
                    @"CREATE\s+TABLE\s+(?:\[[^\]]+\]|[A-Za-z0-9_]+\.)?\[?([A-Za-z0-9_]+)\]?",
                    RegexOptions.IgnoreCase);

                foreach (Match match in regex.Matches(schemaContent))
                {
                    if (match.Success && match.Groups.Count > 1 &&
                        !string.IsNullOrWhiteSpace(match.Groups[1].Value))
                    {
                        tableNames.Add(match.Groups[1].Value.Trim());
                    }
                }
            }
            catch (InvalidOperationException)
            {
                return Result<HashSet<string>>.Failure("The supplied schema has an invalid structure.");
            }

            return tableNames.Count == 0
                ? Result<HashSet<string>>.Failure("No tables could be extracted from the supplied schema.")
                : Result<HashSet<string>>.Success(tableNames);
        }

        public async Task<Result<bool>> ToggleTablePermissionAsync(Guid layerId, string tableName, bool isAllowed, CancellationToken cancellationToken = default)
        {
            if (string.IsNullOrWhiteSpace(tableName))
                return Result<bool>.Failure("Table name cannot be empty.");

            try
            {
                var table = await _context.AllowedTables
                    .FirstOrDefaultAsync(t => t.SemanticLayerId == layerId && t.TableName.ToLower() == tableName.ToLower(), cancellationToken);

                if (table == null)
                    return Result<bool>.Failure($"NOT_FOUND: Table '{tableName}' was not found in the specified layer.");

                table.IsAllowed = isAllowed;
                await _context.SaveChangesAsync(cancellationToken);

                _cache.Remove(AllowedTablesCacheKey(layerId));

                return Result<bool>.Success(true);
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error toggling permission for table {TableName} in layer {LayerId}", tableName, layerId);
                return Result<bool>.Failure("DATABASE_ERROR: Failed to update permission.");
            }
        }

        public async Task<Result<bool>> ToggleUserTablePermissionAsync(
            Guid layerId,
            string email,
            string tableName,
            bool isAllowed,
            CancellationToken cancellationToken = default)
        {
            if (string.IsNullOrWhiteSpace(email))
                return Result<bool>.Failure("User email cannot be empty.");

            if (string.IsNullOrWhiteSpace(tableName))
                return Result<bool>.Failure("Table name cannot be empty.");

            try
            {
                var normalizedEmail = email.Trim();
                var user = await _context.Users
                    .FirstOrDefaultAsync(item => item.Email.ToLower() == normalizedEmail.ToLower(), cancellationToken);

                if (user == null)
                    return Result<bool>.Failure("NOT_FOUND: User was not found.");

                var normalizedTableName = tableName.Trim();
                var tableExists = await _context.AllowedTables
                    .AnyAsync(table => table.SemanticLayerId == layerId &&
                        table.TableName.ToLower() == normalizedTableName.ToLower(), cancellationToken);

                if (!tableExists)
                    return Result<bool>.Failure($"NOT_FOUND: Table '{normalizedTableName}' was not found in the specified layer.");

                var permission = await _context.UserTablePermissions
                    .FirstOrDefaultAsync(item => item.UserId == user.Id &&
                        item.SemanticLayerId == layerId &&
                        item.TableName.ToLower() == normalizedTableName.ToLower(), cancellationToken);

                if (permission == null)
                {
                    _context.UserTablePermissions.Add(new UserTablePermission
                    {
                        UserId = user.Id,
                        SemanticLayerId = layerId,
                        TableName = normalizedTableName,
                        IsAllowed = isAllowed
                    });
                }
                else
                {
                    permission.IsAllowed = isAllowed;
                }

                await _context.SaveChangesAsync(cancellationToken);
                return Result<bool>.Success(true);
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error toggling table permission for user {Email}, table {TableName}, layer {LayerId}", email, tableName, layerId);
                return Result<bool>.Failure("DATABASE_ERROR: Failed to update user table permission.");
            }
        }

        public async Task<Result<bool>> ActivateSemanticLayerAsync(Guid layerId, CancellationToken cancellationToken = default)
        {
            var targetLayer = await _context.SemanticLayers
                .FirstOrDefaultAsync(sl => sl.Id == layerId, cancellationToken);

            if (targetLayer == null)
                return Result<bool>.Failure("Semantic Layer not found.");

            var hasApprovedRevision = await _context.SemanticRevisions
                .AnyAsync(r => r.SemanticLayerId == layerId && r.Status == "Approved", cancellationToken);

            if (!hasApprovedRevision)
                return Result<bool>.Failure("Cannot activate semantic layer without an approved revision.");

            if (targetLayer.IsActive)
            {
                return Result<bool>.Success(true);
            }

            var activeLayers = await _context.SemanticLayers
                .Where(sl => sl.IsActive && sl.Id != layerId)
                .ToListAsync(cancellationToken);

            foreach (var layer in activeLayers)
            {
                layer.IsActive = false;
            }

            try
            {
                // The filtered unique index on IsActive allows only one active
                // layer. Persist the deactivation first so SQL Server never
                // observes two active layers in the same update batch.
                await _context.SaveChangesAsync(cancellationToken);

                targetLayer.IsActive = true;
                await _context.SaveChangesAsync(cancellationToken);
            }
            catch (DbUpdateException ex)
            {
                _logger.LogError(
                    ex,
                    "Failed to activate semantic layer {LayerId}. Database error: {DatabaseError}",
                    layerId,
                    ex.InnerException?.Message ?? ex.Message);
                return Result<bool>.Failure("DATABASE_ERROR: Failed to activate the semantic layer. Check the backend logs for the database error.");
            }

            _cache.Remove(AllowedTablesCacheKey(layerId));

            var currentUser = _currentUserService.UserId ?? "SYSTEM";

            await _auditService.LogEventAsync(
                action: AuditActions.SemanticLayerActivation,
                userId: currentUser,
                status: "Success",
                resourceId: targetLayer.Id.ToString(),
                cancellationToken: cancellationToken
            );

            return Result<bool>.Success(true);
        }
    }
}
