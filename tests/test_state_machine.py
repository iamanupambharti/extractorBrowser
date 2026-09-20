"""
Unit tests for the StateMachine transitions and legality.
"""
import pytest
from core.state_machine import StateMachine, JobState, InvalidStateTransitionError

def test_initial_state_queued():
    sm = StateMachine(JobState.QUEUED)
    assert sm.current_state == JobState.QUEUED
    assert len(sm.history) == 1

def test_valid_forward_progression():
    sm = StateMachine(JobState.QUEUED)
    sm.transition_to(JobState.VALIDATING_INPUT)
    assert sm.current_state == JobState.VALIDATING_INPUT
    sm.transition_to(JobState.STARTING_BROWSER)
    assert sm.current_state == JobState.STARTING_BROWSER
    sm.transition_to(JobState.UPLOADING)
    assert sm.current_state == JobState.UPLOADING
    sm.transition_to(JobState.CONFIRMING_ATTACHMENT)
    sm.transition_to(JobState.SUBMITTING)
    sm.transition_to(JobState.WAITING_FOR_RESPONSE)
    sm.transition_to(JobState.CAPTURING_RESPONSE)
    sm.transition_to(JobState.RAW_RESPONSE_SAVED)
    sm.transition_to(JobState.PARSING_JSON)
    sm.transition_to(JobState.VALIDATING_SCHEMA)
    sm.transition_to(JobState.COMPLETED)
    assert sm.is_terminal

def test_illegal_state_jump_raises():
    sm = StateMachine(JobState.QUEUED)
    with pytest.raises(InvalidStateTransitionError):
        # Cannot jump straight from QUEUED to COMPLETED
        sm.transition_to(JobState.COMPLETED)

def test_cancellation_from_queued():
    sm = StateMachine(JobState.QUEUED)
    sm.transition_to(JobState.CANCELLED)
    assert sm.current_state == JobState.CANCELLED
    assert sm.is_terminal

def test_terminal_state_cannot_transition():
    sm = StateMachine(JobState.COMPLETED)
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(JobState.QUEUED)
