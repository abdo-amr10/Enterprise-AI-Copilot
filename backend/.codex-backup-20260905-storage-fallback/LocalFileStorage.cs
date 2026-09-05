using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.Common.Models;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace EnterpriseAiCopilot.Infrastructure.FileStorage
{
    public class LocalFileStorage : IFileStorage
    {
        private readonly string _baseStoragePath;

        public LocalFileStorage(IConfiguration configuration, IHostEnvironment environment)
        {
            var configuredRoot = configuration["FileStorage:BasePath"];
            var storageRoot = string.IsNullOrWhiteSpace(configuredRoot)
                ? Path.Combine(AppContext.BaseDirectory, "Storage")
                : configuredRoot;

            if (!Path.IsPathFullyQualified(storageRoot))
                throw new InvalidOperationException("FileStorage:BasePath must resolve to an absolute persistent path.");

            _baseStoragePath = Path.GetFullPath(storageRoot)
                .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);

            Directory.CreateDirectory(_baseStoragePath);
        }

        public async Task<Result<string>> SaveFileAsync(IFormFile file, string directoryName, CancellationToken cancellationToken = default)
        {
            if (file == null || file.Length == 0)
                return Result<string>.Failure("File is empty or null.");

            try
            {
                var targetDirectory = ResolveContainedPath(directoryName);
                if (!Directory.Exists(targetDirectory))
                {
                    Directory.CreateDirectory(targetDirectory);
                }

                var safeFileName = Path.GetFileName(file.FileName);
                var uniqueFileName = $"{Guid.NewGuid()}_{safeFileName}";
                var filePath = Path.Combine(targetDirectory, uniqueFileName);

                using (var stream = new FileStream(filePath, FileMode.Create))
                {
                    await file.CopyToAsync(stream, cancellationToken);
                }

                var relativePath = Path.Combine(directoryName, uniqueFileName).Replace("\\", "/");
                return Result<string>.Success(relativePath);
            }
            catch (Exception ex)
            {
                return Result<string>.Failure($"An error occurred while saving the file: {ex.Message}");
            }
        }

        public async Task<Result<byte[]>> GetFileAsync(string relativeFilePath, CancellationToken cancellationToken = default)
        {
            var fullPath = ResolveContainedPath(relativeFilePath);
            if (!File.Exists(fullPath))
                return Result<byte[]>.Failure("File not found on disk.");

            try
            {
                var bytes = await File.ReadAllBytesAsync(fullPath, cancellationToken);
                return Result<byte[]>.Success(bytes);
            }
            catch (Exception ex)
            {
                return Result<byte[]>.Failure($"An error occurred while reading the file: {ex.Message}");
            }
        }

        public Task<Result<bool>> DeleteFileAsync(string relativeFilePath, CancellationToken cancellationToken = default)
        {
            try
            {
                var fullPath = ResolveContainedPath(relativeFilePath);

                if (File.Exists(fullPath))
                {
                    File.Delete(fullPath);
                    return Task.FromResult(Result<bool>.Success(true));
                }

                return Task.FromResult(Result<bool>.Success(true));
            }
            catch (Exception ex)
            {
                return Task.FromResult(Result<bool>.Failure($"Error deleting file: {ex.Message}"));
            }
        }

        private string ResolveContainedPath(string relativePath)
        {
            if (string.IsNullOrWhiteSpace(relativePath))
                throw new ArgumentException("Storage path cannot be empty.", nameof(relativePath));

            var fullPath = Path.GetFullPath(Path.Combine(_baseStoragePath, relativePath));
            var rootWithSeparator = _baseStoragePath + Path.DirectorySeparatorChar;

            if (!fullPath.StartsWith(rootWithSeparator, StringComparison.OrdinalIgnoreCase) &&
                !string.Equals(fullPath, _baseStoragePath, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("Storage path escapes the configured storage root.");
            }

            return fullPath;
        }
    }
}
