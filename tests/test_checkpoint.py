"""
Unit tests for database logging, checkpoints, and resume state determination.
"""
import pytest
from core.state_machine import JobState
from storage.database import Database
from storage.artifacts import ArtifactManager
from core.checkpoint import CheckpointManager

def test_database_job_creation_and_transitions(tmp_path):
    db_file = tmp_path / "test.db"
    db_inst = Database(db_file)
    art_inst = ArtifactManager()

    job = db_inst.create_job(
        job_id="job_unit_001",
        source_filename="test_paper.pdf",
        source_sha256="abc12345def",
        source_size_bytes=1024,
        source_page_count=2,
    )
    assert job["id"] == "job_unit_001"
    assert job["status"] == JobState.QUEUED.value

    # Record a transition
    db_inst.record_transition("job_unit_001", JobState.QUEUED.value, JobState.VALIDATING_INPUT.value, "Validating")
    updated = db_inst.get_job("job_unit_001")
    assert updated["status"] == JobState.VALIDATING_INPUT.value

    transitions = db_inst.get_job_transitions("job_unit_001")
    assert len(transitions) == 2

def test_checkpoint_determine_resume_state(tmp_path):
    db_file = tmp_path / "test_resume.db"
    db_inst = Database(db_file)
    art_inst = ArtifactManager()
    cp = CheckpointManager(database=db_inst, artifact_manager=art_inst)

    job = db_inst.create_job(
        job_id="job_resume_001",
        source_filename="sample.pdf",
        source_sha256="12345678",
    )

    # Initial resume state
    state, msg = cp.determine_resume_state("job_resume_001")
    assert state == JobState.QUEUED
