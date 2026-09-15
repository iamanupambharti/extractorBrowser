"""
Checkpoint and crash recovery manager for ExamForge Browser.
Ensures every critical transition is persisted and allows safe resumption.
"""
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from core.state_machine import JobState
from storage.database import db
from storage.artifacts import artifacts
from core.logging_config import logger

class CheckpointManager:
    """Coordinates state persistence and crash recovery."""
    def __init__(self, database=db, artifact_manager=artifacts):
        self.db = database
        self.artifacts = artifact_manager

    def record_checkpoint(
        self,
        job_id: str,
        target_state: JobState,
        note: str = "",
        raw_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
        report_path: Optional[Path] = None,
    ) -> None:
        """Persist a checkpoint and record artifacts atomically."""
        job = self.db.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        current_status = job.get("status")
        # Update artifacts in database if provided
        self.db.update_job_artifacts(
            job_id,
            raw_path=str(raw_path) if raw_path else None,
            output_path=str(output_path) if output_path else None,
            report_path=str(report_path) if report_path else None,
        )

        # Record state transition in DB
        self.db.record_transition(
            job_id=job_id,
            from_state=current_status,
            to_state=target_state.value,
            note=note,
        )
        logger.info(f"Checkpoint saved for {job_id}: {current_status} -> {target_state.value} ({note})")

    def determine_resume_state(self, job_id: str) -> Tuple[JobState, str]:
        """
        Inspects stored artifacts and DB status to find the safe state to resume from.
        Avoids duplicate submissions if a response already exists.
        """
        job = self.db.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        status_str = job.get("status")
        source_filename = job.get("source_filename")

        # Check existing filesystem artifacts
        raw_path = self.artifacts.get_raw_path(job_id, source_filename)
        output_path = self.artifacts.get_output_path(job_id, source_filename)
        report_path = self.artifacts.get_report_path(job_id, source_filename)

        if output_path.exists() and report_path.exists():
            return JobState.COMPLETED, "Both output and validation report exist on disk."

        if raw_path.exists() and raw_path.stat().st_size > 0:
            return JobState.RAW_RESPONSE_SAVED, "Raw response exists on disk; resume directly to parsing."

        # If it was interrupted during browser interaction
        if status_str in {
            JobState.SUBMITTING.value,
            JobState.WAITING_FOR_RESPONSE.value,
            JobState.CAPTURING_RESPONSE.value,
        }:
            return (
                JobState.NEEDS_USER_ACTION,
                "Job was interrupted after submission; requires user inspection of browser conversation to prevent double submission.",
            )

        if status_str in {
            JobState.UPLOADING.value,
            JobState.CONFIRMING_ATTACHMENT.value,
        }:
            return JobState.WAITING_FOR_USER_READY, "Interrupted during upload; return to user ready state."

        # Otherwise map to current status enum
        try:
            return JobState(status_str), f"Resuming from current state {status_str}"
        except ValueError:
            return JobState.NEEDS_USER_ACTION, f"Unknown status '{status_str}'; paused for safety."

checkpoint_manager = CheckpointManager()
