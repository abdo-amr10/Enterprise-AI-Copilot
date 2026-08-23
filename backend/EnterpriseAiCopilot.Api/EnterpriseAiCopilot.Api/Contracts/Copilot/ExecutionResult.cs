using System.Text.Json;

namespace EnterpriseAiCopilot.Api.Contracts.Copilot;

/// <summary>
/// The normalized, complete result returned by the Backend SQL executor.
/// This is private to Backend-to-AI communication; it must never come from
/// the browser.
/// </summary>
public sealed record ExecutionResult(
    string Status,
    IReadOnlyList<string> Columns,
    IReadOnlyList<IReadOnlyList<JsonElement>> Rows,
    int? RowCount = null,
    string? ErrorCode = null,
    string? ErrorMessage = null,
    IReadOnlyDictionary<string, JsonElement>? Metadata = null);

public sealed record PostQueryFormatRequest(string Question, ExecutionResult ExecutionResult);

/// <summary>
/// Result returned by AI after presentation formatting. For Excel responses,
/// FileContentBase64 is a transport encoding: the Backend or UI decodes it to
/// a normal .xlsx file and never displays the Base64 text to the user.
/// </summary>
public sealed record FormattedExecutionResult(
    string Status,
    string PresentationType,
    string Text,
    IReadOnlyList<string> Columns,
    IReadOnlyList<IReadOnlyList<JsonElement>> Rows,
    int RowCount,
    string? FileName = null,
    string? ContentType = null,
    string? FileContentBase64 = null,
    string? ErrorCode = null);
