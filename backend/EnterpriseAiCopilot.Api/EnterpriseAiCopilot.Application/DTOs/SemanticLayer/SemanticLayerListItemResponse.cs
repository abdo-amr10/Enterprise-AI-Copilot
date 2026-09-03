namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer
{
    public class SemanticLayerListItemResponse
    {
        public string SemanticLayerId { get; set; } = string.Empty;
        public string Name { get; set; } = string.Empty;
        public string DatabaseName { get; set; } = string.Empty;
        public string Description { get; set; } = string.Empty;
        public bool IsActive { get; set; }
        public bool HasApprovedRevision { get; set; }
    }
}
