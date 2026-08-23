using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.Common.Models;
using EnterpriseAiCopilot.Application.DTOs;
using EnterpriseAiCopilot.Application.DTOs.SemanticLayer;
using EnterpriseAiCopilot.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
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

        public SemanticLayerService(
            IApplicationDbContext context,
            IFileStorage fileStorage,
            ICurrentUserService currentUserService,
            IAiSemanticClient aiSemanticClient) 
        {
            _context = context;
            _fileStorage = fileStorage;
            _currentUserService = currentUserService;
            _aiSemanticClient = aiSemanticClient;
        }

        public async Task<Result<UploadDataSourcesResponse>> UploadDataSourcesAsync(UploadDataSourcesRequest request, CancellationToken cancellationToken = default)
        {
            if (request.SchemaFile == null || request.SchemaFile.Length == 0)
                return Result<UploadDataSourcesResponse>.Failure("Schema file is strictly required and cannot be empty.");

            var currentUser = _currentUserService.Email ?? "System_Admin";

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
                FileType = Path.GetExtension(request.SchemaFile.FileName).TrimStart('.'),
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
                    FileType = Path.GetExtension(request.DocumentationFile.FileName).TrimStart('.'),
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
                    FileType = Path.GetExtension(request.GlossaryFile.FileName).TrimStart('.'),
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
                    FileType = Path.GetExtension(request.SampleDataFile.FileName).TrimStart('.'),
                    FileSize = request.SampleDataFile.Length,
                    StoragePath = sampleResult.Data!,
                    UploadedBy = currentUser,
                    SemanticLayerId = semanticLayer.Id
                };
                _context.SemanticSourceFiles.Add(sampleDataFile);
            }

            await _context.SaveChangesAsync(cancellationToken);

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

            return Result<UploadDataSourcesResponse>.Success(response);
        }

        public async Task<Result<GenerateDraftResponse>> GenerateDraftAsync(GenerateDraftRequest request, CancellationToken cancellationToken = default)
        {
            if (!Guid.TryParse(request.SemanticLayerId, out Guid layerId))
                return Result<GenerateDraftResponse>.Failure("Invalid SemanticLayerId format.");

            var semanticLayer = await _context.SemanticLayers
                .Include(s => s.Revisions)
                .FirstOrDefaultAsync(s => s.Id == layerId, cancellationToken);

            if (semanticLayer == null)
                return Result<GenerateDraftResponse>.Failure("Semantic Layer not found.");

            var aiDraftResult = await _aiSemanticClient.GenerateDraftAsync(request, cancellationToken);
            if (!aiDraftResult.IsSuccess)
                return Result<GenerateDraftResponse>.Failure($"AI_RUNTIME_ERROR: Failed to generate draft. {aiDraftResult.ErrorMessage}");

            string generatedJson = aiDraftResult.ContentJson ?? "{}";

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

            var aiReviewResult = await _aiSemanticClient.ReviewDraftAsync(request.RevisionId, request.Decision, request.Comments, cancellationToken);
            if (!aiReviewResult.IsSuccess)
                return Result<ReviewRevisionResponse>.Failure($"AI_RUNTIME_ERROR: Failed to submit review to AI. {aiReviewResult.ErrorMessage}");

            var currentUser = _currentUserService.Email ?? "System_Admin";
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
                var semanticLayer = await _context.SemanticLayers.FindAsync(new object[] { layerId }, cancellationToken);
                if (semanticLayer != null) semanticLayer.IsActive = true;

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

            await _context.SaveChangesAsync(cancellationToken);

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

            string fileContentStr = System.Text.Encoding.UTF8.GetString(fileResult.Data);
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
                .OrderByDescending(s => s.CreatedAt)
                .FirstOrDefaultAsync(cancellationToken);

            if (semanticLayer == null)
                return Result<SemanticLayerStatusResponse>.Failure("No Semantic Layer found.");

            var latestRevision = semanticLayer.Revisions
                .OrderByDescending(r => r.VersionNumber)
                .FirstOrDefault();

            if (latestRevision == null)
                return Result<SemanticLayerStatusResponse>.Failure("No revisions found for the current Semantic Layer.");

            var response = new SemanticLayerStatusResponse
            {
                SemanticLayerId = semanticLayer.Id.ToString(),
                Status = latestRevision.Status,
                Version = latestRevision.Status == "Approved" ? $"v{latestRevision.VersionNumber}.0" : "draft",
                RevisionId = latestRevision.Id.ToString(),
                BuildTimestamp = latestRevision.CreatedAt.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                LastRegenerationType = string.IsNullOrEmpty(latestRevision.RegenerationType) ? "Unknown" : latestRevision.RegenerationType
            };

            return Result<SemanticLayerStatusResponse>.Success(response);
        }

        public async Task<Result<bool>> DeleteSemanticLayerAsync(Guid layerId, CancellationToken cancellationToken = default)
        {
            var semanticLayer = await _context.SemanticLayers
                .Include(s => s.SourceFiles)
                .FirstOrDefaultAsync(s => s.Id == layerId, cancellationToken);

            if (semanticLayer == null)
                return Result<bool>.Failure("Semantic Layer not found.");

            if (semanticLayer.SourceFiles != null && semanticLayer.SourceFiles.Any())
            {
                foreach (var file in semanticLayer.SourceFiles)
                {
                    await _fileStorage.DeleteFileAsync(file.StoragePath, cancellationToken);
                }
            }

            _context.SemanticLayers.Remove(semanticLayer);
            await _context.SaveChangesAsync(cancellationToken);

            return Result<bool>.Success(true);
        }

        public async Task<Result<bool>> DeleteSourceFileAsync(Guid fileId, CancellationToken cancellationToken = default)
        {
            var sourceFile = await _context.SemanticSourceFiles
                .FirstOrDefaultAsync(f => f.Id == fileId, cancellationToken);

            if (sourceFile == null)
                return Result<bool>.Failure("File not found.");

            var deleteResult = await _fileStorage.DeleteFileAsync(sourceFile.StoragePath, cancellationToken);

            if (!deleteResult.IsSuccess)
                return Result<bool>.Failure($"Failed to delete physical file: {deleteResult.ErrorMessage}");

            _context.SemanticSourceFiles.Remove(sourceFile);
            await _context.SaveChangesAsync(cancellationToken);

            return Result<bool>.Success(true);
        }

        public async Task<Result<RetrieveSourceFileResponse>> UpsertSourceFileAsync(Guid layerId, Guid? fileId, UpsertSourceFileRequest request, CancellationToken cancellationToken = default)
        {
            var allowedTypes = new[] { "schema", "documentation", "glossary", "sampledata" };
            if (!string.IsNullOrEmpty(request.FileType) && !allowedTypes.Contains(request.FileType, StringComparer.OrdinalIgnoreCase))
            {
                return Result<RetrieveSourceFileResponse>.Failure($"Invalid fileType. Allowed values are: schema, documentation, glossary, sampledata.");
            }

            if (request.File == null || request.File.Length == 0)
                return Result<RetrieveSourceFileResponse>.Failure("File is required and cannot be empty.");

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
            else if (!string.IsNullOrEmpty(request.FileType))
            {
                targetFile = semanticLayer.SourceFiles.FirstOrDefault(f => f.FileType.Equals(request.FileType, StringComparison.OrdinalIgnoreCase));
            }

            var folderName = $"SemanticSources/Layer_{semanticLayer.Id}";
            var currentUser = _currentUserService.Email ?? "System_Admin";

            if (targetFile != null)
            {
                await _fileStorage.DeleteFileAsync(targetFile.StoragePath, cancellationToken);

                var uploadResult = await _fileStorage.SaveFileAsync(request.File, folderName, cancellationToken);
                if (!uploadResult.IsSuccess)
                    return Result<RetrieveSourceFileResponse>.Failure($"Failed to upload new file: {uploadResult.ErrorMessage}");

                targetFile.FileName = request.File.FileName;
                targetFile.FileType = !string.IsNullOrEmpty(request.FileType) ? request.FileType.ToLower() : Path.GetExtension(request.File.FileName).TrimStart('.');
                targetFile.FileSize = request.File.Length;
                targetFile.StoragePath = uploadResult.Data!;
                targetFile.UploadedBy = currentUser;
            }
            else
            {
                var uploadResult = await _fileStorage.SaveFileAsync(request.File, folderName, cancellationToken);
                if (!uploadResult.IsSuccess)
                    return Result<RetrieveSourceFileResponse>.Failure($"Failed to upload file: {uploadResult.ErrorMessage}");

                targetFile = new SemanticSourceFile
                {
                    FileName = request.File.FileName,
                    FileType = !string.IsNullOrEmpty(request.FileType) ? request.FileType.ToLower() : Path.GetExtension(request.File.FileName).TrimStart('.'),
                    FileSize = request.File.Length,
                    StoragePath = uploadResult.Data!,
                    UploadedBy = currentUser,
                    SemanticLayerId = semanticLayer.Id
                };

                _context.SemanticSourceFiles.Add(targetFile);
            }

            await _context.SaveChangesAsync(cancellationToken);

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
    }
}