namespace EnterpriseAiCopilot.Application.DTOs.Admin;

public sealed class AdminDashboardMetricsResponse
{
    public int ActiveUsers { get; set; }
    public int QuestionsToday { get; set; }
    public int TotalUsers { get; set; }
    public DateTime AsOfUtc { get; set; }
}
