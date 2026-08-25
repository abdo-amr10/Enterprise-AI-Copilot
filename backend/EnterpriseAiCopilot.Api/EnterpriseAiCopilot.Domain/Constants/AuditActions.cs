using System;
using System.Collections.Generic;
using System.Text;

namespace EnterpriseAiCopilot.Domain.Constants
{
    public static class AuditActions
    {
        // (Identity & Access)
        public const string UserLogin = "UserLogin";
        public const string UserRegistration = "UserRegistration";

        // (Semantic Layer Management)
        public const string SemanticLayerUpload = "SemanticLayerUpload"; 
        public const string SemanticLayerDraftGeneration = "SemanticLayerDraftGeneration";
        public const string SemanticLayerApproval = "Semantic LayerApproval"; 
        public const string SemanticLayerRejection = "Semantic LayerRejection"; 
        public const string SemanticLayerSubmission = "SemanticLayerSubmission"; 

        // (Copilot Execution)
        public const string QueryExecution = "QueryExecution";
        public const string QueryFailed = "QueryFailed"; 
    }
}
