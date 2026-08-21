using EnterpriseAiCopilot.Application.Common.Models;
using Microsoft.AspNetCore.Http;
using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.Common.Interfaces
{
    public interface IFileStorage
    {
        Task<Result<string>> SaveFileAsync(IFormFile file, string directoryName, CancellationToken cancellationToken = default);
        Task<Result<byte[]>> GetFileAsync(string relativeFilePath, CancellationToken cancellationToken = default);
        Task<Result<bool>> DeleteFileAsync(string relativeFilePath, CancellationToken cancellationToken = default);
    }
}
