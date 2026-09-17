"""
Finite State Machine for ExamForge Browser Jobs.
Strictly governs state transitions, error statuses, and terminal states.
"""
from enum import Enum
from typing import Set, Dict, List
from datetime import datetime

class JobState(str, Enum):
    QUEUED = "QUEUED"
    VALIDATING_INPUT = "VALIDATING_INPUT"
    STARTING_BROWSER = "STARTING_BROWSER"
    WAITING_FOR_AUTH = "WAITING_FOR_AUTH"
    WAITING_FOR_USER_READY = "WAITING_FOR_USER_READY"
    UPLOADING = "UPLOADING"
    CONFIRMING_ATTACHMENT = "CONFIRMING_ATTACHMENT"
    SUBMITTING = "SUBMITTING"
    WAITING_FOR_RESPONSE = "WAITING_FOR_RESPONSE"
    CAPTURING_RESPONSE = "CAPTURING_RESPONSE"
    RAW_RESPONSE_SAVED = "RAW_RESPONSE_SAVED"
    PARSING_JSON = "PARSING_JSON"
    VALIDATING_SCHEMA = "VALIDATING_SCHEMA"
    CONTENT_REVIEW_REQUIRED = "CONTENT_REVIEW_REQUIRED"
    COMPLETED = "COMPLETED"
    NEEDS_USER_ACTION = "NEEDS_USER_ACTION"
    PAUSED_USAGE_LIMIT = "PAUSED_USAGE_LIMIT"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    CANCELLED = "CANCELLED"

# Terminal states cannot transition further (unless explicit reprocess/retry is triggered)
TERMINAL_STATES: Set[JobState] = {
    JobState.COMPLETED,
    JobState.FAILED_PERMANENT,
    JobState.CANCELLED,
}

# Legal forward/recovery transitions map
ALLOWED_TRANSITIONS: Dict[JobState, Set[JobState]] = {
    JobState.QUEUED: {
        JobState.VALIDATING_INPUT,
        JobState.CANCELLED,
        JobState.FAILED_PERMANENT,
    },
    JobState.VALIDATING_INPUT: {
        JobState.STARTING_BROWSER,
        JobState.NEEDS_USER_ACTION,
        JobState.FAILED_PERMANENT,
        JobState.CANCELLED,
    },
    JobState.STARTING_BROWSER: {
        JobState.WAITING_FOR_AUTH,
        JobState.WAITING_FOR_USER_READY,
        JobState.UPLOADING,
        JobState.FAILED_RETRYABLE,
        JobState.FAILED_PERMANENT,
        JobState.NEEDS_USER_ACTION,
        JobState.CANCELLED,
    },
    JobState.WAITING_FOR_AUTH: {
        JobState.WAITING_FOR_USER_READY,
        JobState.UPLOADING,
        JobState.NEEDS_USER_ACTION,
        JobState.CANCELLED,
    },
    JobState.WAITING_FOR_USER_READY: {
        JobState.UPLOADING,
        JobState.SUBMITTING,
        JobState.NEEDS_USER_ACTION,
        JobState.CANCELLED,
    },
    JobState.UPLOADING: {
        JobState.CONFIRMING_ATTACHMENT,
        JobState.NEEDS_USER_ACTION,
        JobState.FAILED_RETRYABLE,
        JobState.FAILED_PERMANENT,
        JobState.CANCELLED,
    },
    JobState.CONFIRMING_ATTACHMENT: {
        JobState.SUBMITTING,
        JobState.NEEDS_USER_ACTION,
        JobState.FAILED_RETRYABLE,
        JobState.FAILED_PERMANENT,
        JobState.CANCELLED,
    },
    JobState.SUBMITTING: {
        JobState.WAITING_FOR_RESPONSE,
        JobState.NEEDS_USER_ACTION,
        JobState.FAILED_RETRYABLE,
        JobState.FAILED_PERMANENT,
        JobState.CANCELLED,
    },
    JobState.WAITING_FOR_RESPONSE: {
        JobState.CAPTURING_RESPONSE,
        JobState.PAUSED_USAGE_LIMIT,
        JobState.NEEDS_USER_ACTION,
        JobState.FAILED_RETRYABLE,
        JobState.FAILED_PERMANENT,
        JobState.CANCELLED,
    },
    JobState.CAPTURING_RESPONSE: {
        JobState.RAW_RESPONSE_SAVED,
        JobState.NEEDS_USER_ACTION,
        JobState.FAILED_RETRYABLE,
        JobState.FAILED_PERMANENT,
        JobState.CANCELLED,
    },
    JobState.RAW_RESPONSE_SAVED: {
        JobState.PARSING_JSON,
        JobState.NEEDS_USER_ACTION,
        JobState.FAILED_PERMANENT,
        JobState.CANCELLED,
    },
    JobState.PARSING_JSON: {
        JobState.VALIDATING_SCHEMA,
        JobState.NEEDS_USER_ACTION,
        JobState.FAILED_PERMANENT,
        JobState.CANCELLED,
    },
    JobState.VALIDATING_SCHEMA: {
        JobState.COMPLETED,
        JobState.CONTENT_REVIEW_REQUIRED,
        JobState.NEEDS_USER_ACTION,
        JobState.FAILED_PERMANENT,
        JobState.CANCELLED,
    },
    JobState.CONTENT_REVIEW_REQUIRED: {
        JobState.COMPLETED,
        JobState.NEEDS_USER_ACTION,
        JobState.CANCELLED,
    },
    # Recovery and Paused states
    JobState.NEEDS_USER_ACTION: {
        JobState.WAITING_FOR_AUTH,
        JobState.WAITING_FOR_USER_READY,
        JobState.UPLOADING,
        JobState.CONFIRMING_ATTACHMENT,
        JobState.SUBMITTING,
        JobState.WAITING_FOR_RESPONSE,
        JobState.CAPTURING_RESPONSE,
        JobState.RAW_RESPONSE_SAVED,
        JobState.PARSING_JSON,
        JobState.VALIDATING_SCHEMA,
        JobState.CONTENT_REVIEW_REQUIRED,
        JobState.CANCELLED,
        JobState.FAILED_PERMANENT,
    },
    JobState.PAUSED_USAGE_LIMIT: {
        JobState.WAITING_FOR_RESPONSE,
        JobState.SUBMITTING,
        JobState.NEEDS_USER_ACTION,
        JobState.CANCELLED,
    },
    JobState.FAILED_RETRYABLE: {
        JobState.STARTING_BROWSER,
        JobState.UPLOADING,
        JobState.SUBMITTING,
        JobState.WAITING_FOR_RESPONSE,
        JobState.CAPTURING_RESPONSE,
        JobState.PARSING_JSON,
        JobState.FAILED_PERMANENT,
        JobState.CANCELLED,
    },
    # Terminal states
    JobState.COMPLETED: set(),
    JobState.FAILED_PERMANENT: set(),
    JobState.CANCELLED: set(),
}

class InvalidStateTransitionError(Exception):
    """Raised when an illegal transition is attempted."""
    pass

class StateMachine:
    """Manages state transitions for a job, validating rules and tracking history."""
    def __init__(self, initial_state: JobState = JobState.QUEUED):
        self.current_state = initial_state
        self.history: List[dict] = [{
            "from_state": None,
            "to_state": initial_state.value,
            "timestamp": datetime.utcnow().isoformat(),
            "note": "Initial state",
        }]

    def can_transition_to(self, target_state: JobState) -> bool:
        """Check if transition to target_state is legally allowed."""
        allowed = ALLOWED_TRANSITIONS.get(self.current_state, set())
        return target_state in allowed

    def transition_to(self, target_state: JobState, note: str = "") -> JobState:
        """Execute a state transition if valid, otherwise raise InvalidStateTransitionError."""
        if not self.can_transition_to(target_state):
            raise InvalidStateTransitionError(
                f"Illegal state transition from {self.current_state.value} to {target_state.value}. "
                f"Allowed transitions: {[s.value for s in ALLOWED_TRANSITIONS.get(self.current_state, set())]}"
            )
        old_state = self.current_state
        self.current_state = target_state
        self.history.append({
            "from_state": old_state.value,
            "to_state": target_state.value,
            "timestamp": datetime.utcnow().isoformat(),
            "note": note,
        })
        return self.current_state

    @property
    def is_terminal(self) -> bool:
        return self.current_state in TERMINAL_STATES
