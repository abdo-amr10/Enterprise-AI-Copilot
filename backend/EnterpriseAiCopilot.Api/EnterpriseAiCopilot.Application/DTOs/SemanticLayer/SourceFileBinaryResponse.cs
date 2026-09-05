namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer;

public class SourceFileBinaryResponse
{
    public byte[] Content { get; set; } = [];
    public string FileName { get; set; } = string.Empty;
    public string ContentType { get; set; } = "application/octet-stream";
}
