using EnterpriseAiCopilot.Application.Common.Interfaces;
using EnterpriseAiCopilot.Application.Common.Models;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Infrastructure.FileStorage
{
    public class LocalFileStorage : IFileStorage
    {
        private readonly string _baseStoragePath;

        public LocalFileStorage(IConfiguration configuration)
        {
            var baseDir = AppDomain.CurrentDomain.BaseDirectory;
            var folderNameFromConfig = configuration["FileStorage:BasePath"] ?? "Storage";

            _baseStoragePath = Path.Combine(baseDir, folderNameFromConfig);
        }

        public async Task<Result<string>> SaveFileAsync(IFormFile file, string directoryName, CancellationToken cancellationToken = default)
        {
            if (file == null || file.Length == 0)
                return Result<string>.Failure("File is empty or null.");

            try
            {
                var targetDirectory = Path.Combine(_baseStoragePath, directoryName);
                if (!Directory.Exists(targetDirectory))
                {
                    Directory.CreateDirectory(targetDirectory);
                }

                var uniqueFileName = $"{Guid.NewGuid()}_{file.FileName}";
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
            var fullPath = Path.Combine(_baseStoragePath, relativeFilePath);
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
                var fullPath = Path.Combine(_baseStoragePath, relativeFilePath);

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
    }
}
