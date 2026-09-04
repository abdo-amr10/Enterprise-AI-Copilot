"""Enums for the Conversation Layer's decision output.

Deliberately plain str Enums (not free-text) so the structured decision
contract (see conversation_decision.py) round-trips cleanly through JSON
without a translation layer, matching how the rest of this codebase
already treats status/classification fields (e.g. ValidationStatus).
"""

from __future__ import annotations

from enum import Enum


class FollowupClassification(str, Enum):
    INDEPENDENT = "INDEPENDENT"
    QUESTION_FOLLOW_UP = "QUESTION_FOLLOW_UP"
    SQL_FOLLOW_UP = "SQL_FOLLOW_UP"
    RESULT_FOLLOW_UP = "RESULT_FOLLOW_UP"
    AMBIGUOUS = "AMBIGUOUS"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class ContextRequirement(str, Enum):
    NONE = "NONE"
    QUESTION_ONLY = "QUESTION_ONLY"
    QUESTION_AND_SQL = "QUESTION_AND_SQL"
    RESULT_ONLY = "RESULT_ONLY"
    QUESTION_AND_RESULT = "QUESTION_AND_RESULT"
    QUESTION_SQL_AND_RESULT = "QUESTION_SQL_AND_RESULT"


class NextAction(str, Enum):
    NL2SQL = "NL2SQL"
    RESULT_RESOLVER = "RESULT_RESOLVER"
    CLARIFICATION = "CLARIFICATION"
    REJECT = "REJECT"


# The field(s) each context requirement actually needs -- used by
# ContextRetriever so it never pulls more than necessary ("retrieve only
# what is required", section 7/15 of the spec).
REQUIREMENT_FIELDS: dict[ContextRequirement, tuple[str, ...]] = {
    ContextRequirement.NONE: (),
    ContextRequirement.QUESTION_ONLY: ("user_question",),
    ContextRequirement.QUESTION_AND_SQL: ("user_question", "generated_sql"),
    ContextRequirement.RESULT_ONLY: ("execution_result_summary",),
    ContextRequirement.QUESTION_AND_RESULT: ("user_question", "execution_result_summary"),
    ContextRequirement.QUESTION_SQL_AND_RESULT: (
        "user_question", "generated_sql", "execution_result_summary",
    ),
}
