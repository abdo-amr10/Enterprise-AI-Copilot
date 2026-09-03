namespace EnterpriseAiCopilot.Application.DTOs.SemanticLayer
{
    public class SemanticRevisionSchemaResponse
    {
        public string SemanticLayerId { get; set; } = string.Empty;
        public string RevisionId { get; set; } = string.Empty;
        public string Status { get; set; } = string.Empty;
        public object Schema { get; set; } = new();
    }
}
