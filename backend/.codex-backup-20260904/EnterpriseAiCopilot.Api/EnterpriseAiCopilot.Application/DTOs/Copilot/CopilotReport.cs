using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Application.DTOs.Copilot
{
    public class CopilotReport
    {
        public string TextSummary { get; set; } = string.Empty;
        public string PresentationType { get; set; } = string.Empty;
        public HeroMetricDto? HeroMetric { get; set; }
        public List<KpiCardDto>? KpiCards { get; set; }
        public TableDataDto? TableData { get; set; }
        public ExcelExportDto? ExcelExport { get; set; }

        public object? Data { get; set; }

    }

    public class HeroMetricDto
    {
        public string Label { get; set; } = string.Empty;
        public string Value { get; set; } = string.Empty;
        public string? DeltaText { get; set; }
    }

    public class KpiCardDto
    {
        public string Label { get; set; } = string.Empty;
        public string Value { get; set; } = string.Empty;
        public string? Subtext { get; set; }
    }

    public class TableDataDto
    {
        public List<string> Columns { get; set; } = new();
        public List<List<object?>> Rows { get; set; } = new();
        public int TotalRows { get; set; }
    }

    public class ExcelExportDto
    {
        public bool Available { get; set; }
        public string? FileName { get; set; }
        public string? ContentType { get; set; }
        public string? FileContentBase64 { get; set; }
    }
}
