"""Authoritative Production Conversation Layer."""

from src.application.services.conversation.continuation import (
    ContinuationResolution,
    ContinuationResolver,
)
from src.application.services.conversation.conversation_layer import ConversationLayer
from src.application.services.conversation.conversation_manager import ConversationManager
from src.application.services.conversation.followup import (
    FollowupConfidence,
    FollowupDetectionResult,
    FollowupDetector,
    FollowupType,
)
from src.application.services.conversation.models import ConversationTurn
from src.application.services.conversation.normalization import RequestNormalizer
from src.application.services.conversation.persistence import BackendStateAdapter
from src.application.services.conversation.replay import (
    ExactReplayManager,
    InMemoryReplayRepository,
    ReplayEntry,
    ReplayResult,
    RequestFingerprint,
    compute_fingerprint,
)
from src.application.services.conversation.result_resolution import (
    ResultResolutionOutcome,
    ResultResolutionStatus,
    ResultResolver,
)
from src.application.services.conversation.router import (
    ConversationRoute,
    ConversationRouter,
    RoutingDecision,
    ScopeEvaluation,
    ScopeGuard,
)
from src.application.services.conversation.state import (
    ConversationState,
    ConversationStateManager,
    ExecutionRecord,
    NegativeResultRecord,
    ResultMetadata,
    SemanticQueryState,
)

__all__ = [
    "BackendStateAdapter",
    "ContinuationResolution",
    "ContinuationResolver",
    "ConversationLayer",
    "ConversationManager",
    "ConversationRoute",
    "ConversationRouter",
    "ConversationState",
    "ConversationStateManager",
    "ConversationTurn",
    "ExactReplayManager",
    "ExecutionRecord",
    "FollowupConfidence",
    "FollowupDetectionResult",
    "FollowupDetector",
    "FollowupType",
    "InMemoryReplayRepository",
    "NegativeResultRecord",
    "ReplayEntry",
    "ReplayResult",
    "RequestFingerprint",
    "RequestNormalizer",
    "ResultMetadata",
    "ResultResolutionOutcome",
    "ResultResolutionStatus",
    "ResultResolver",
    "RoutingDecision",
    "ScopeEvaluation",
    "ScopeGuard",
    "SemanticQueryState",
    "compute_fingerprint",
]
