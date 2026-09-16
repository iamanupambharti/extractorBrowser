"""
Job Manager and central orchestrator for ExamForge Browser.
Enforces single-active-job policy, manages full lifecycle, coordinates browser automation,
checkpoints, error classification, and offline re-parsing.
Supports thread-isolated background execution and auto-detection of manual authentication.
"""
from pathlib import Path
import hashlib
import time
import uuid
import threading
from typing import Optional, Dict, Any, Tuple
import fitz  # PyMuPDF

from core.config import config
from core.state_machine import JobState, StateMachine, InvalidStateTransitionError
from core.checkpoint import checkpoint_manager, CheckpointManager
from core.logging_config import logger
from storage.database import db
from storage.artifacts import artifacts
from validation.parse_response import parse_raw_response
from validation.validate_json import validate_json_schema, validate_with_pydantic
from validation.completeness import check_question_completeness
from validation.quality_flags import audit_question_quality, generate_validation_report
from browser.launch import browser_manager
from browser.gemini_page import GeminiPageAdapter

def calculate_sha256(file_path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()

def inspect_pdf(file_path: Path) -> Tuple[int, int]:
    """
    Validates PDF readability and extracts size and page count.
    Returns:
        (file_size_bytes, page_count)
    """
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    if file_path.suffix.lower() != ".pdf":
        raise ValueError(f"File must have .pdf extension: {file_path}")
    
    size_bytes = file_path.stat().st_size
    if size_bytes == 0:
        raise ValueError(f"PDF file is empty (0 bytes): {file_path}")

    try:
        doc = fitz.open(file_path)
        page_count = doc.page_count
        doc.close()
        return size_bytes, page_count
    except Exception as e:
        raise ValueError(f"PDF is unreadable or corrupted: {e}")

class JobManager:
    """Coordinates job execution, state machine, and browser interactions."""
    def __init__(self, app_config=config, database=db, artifact_mgr=artifacts, checkpoint_mgr=checkpoint_manager):
        self.cfg = app_config
        self.db = database
        self.artifacts = artifact_mgr
        self.checkpoints = checkpoint_mgr if checkpoint_mgr.db == database else CheckpointManager(database, artifact_mgr)
        self.current_job_id: Optional[str] = None
        self._cancel_requested: bool = False
        self._pause_requested: bool = False
        self._active_thread: Optional[threading.Thread] = None

    def get_active_job(self) -> Optional[Dict[str, Any]]:
        return self.db.get_active_job()

    def create_job(self, pdf_path: Path, expected_count: Optional[int] = None) -> Dict[str, Any]:
        """
        Validates PDF input, calculates SHA-256, and creates a new job record.
        Enforces single-active-job constraint.
        """
        active = self.get_active_job()
        if active:
            raise RuntimeError(
                f"Cannot create new job: another job is currently active (ID: {active['id']}, Status: {active['status']})"
            )

        pdf_path = Path(pdf_path)
        size_bytes, page_count = inspect_pdf(pdf_path)
        file_sha256 = calculate_sha256(pdf_path)

        # Unique deterministic job ID: job_<short_sha>_<short_uuid>
        short_hash = file_sha256[:8]
        short_id = uuid.uuid4().hex[:6]
        job_id = f"job_{short_hash}_{short_id}"

        job = self.db.create_job(
            job_id=job_id,
            source_filename=pdf_path.name,
            source_sha256=file_sha256,
            source_size_bytes=size_bytes,
            source_page_count=page_count,
            prompt_version=self.cfg.prompt_version,
            schema_version=self.cfg.schema_version,
            initial_status=JobState.QUEUED,
        )
        self.current_job_id = job_id
        logger.info(f"Created new job: {job_id} for {pdf_path.name} ({page_count} pages)")
        return job

    def cancel_job(self, job_id: str) -> None:
        """Requests cancellation of a running job."""
        self._cancel_requested = True
        self.checkpoints.record_checkpoint(job_id, JobState.CANCELLED, note="Cancelled by user")
        browser_manager.close()
        logger.info(f"Job {job_id} marked as CANCELLED by user.")

    def pause_job(self, job_id: str) -> None:
        """Requests pause of a running job."""
        self._pause_requested = True
        self.checkpoints.record_checkpoint(
            job_id, JobState.NEEDS_USER_ACTION, note="Paused by user"
        )
        logger.info(f"Job {job_id} paused by user.")

    def start_job_async(
        self,
        job_id: str,
        pdf_path: Path,
        expected_count: Optional[int] = None,
    ) -> None:
        """Launches the job pipeline in a dedicated background worker thread."""
        self._cancel_requested = False
        self._pause_requested = False
        self._active_thread = threading.Thread(
            target=self.run_pipeline,
            args=(job_id, pdf_path, expected_count),
            daemon=True,
            name=f"Worker-{job_id}",
        )
        self._active_thread.start()
        logger.info(f"Started background worker thread for job {job_id}")

    def run_pipeline(
        self,
        job_id: str,
        pdf_path: Path,
        expected_count: Optional[int] = None,
        manual_auth_confirm: bool = False
    ) -> Dict[str, Any]:
        """
        Executes the end-to-end browser extraction and validation pipeline.
        Runs entirely on the caller's thread to preserve Playwright connection integrity.
        """
        self._cancel_requested = False
        self._pause_requested = False
        self.current_job_id = job_id
        sm = StateMachine(JobState.QUEUED)

        def step_checkpoint(next_state: JobState, note: str = ""):
            if self._cancel_requested:
                sm.transition_to(JobState.CANCELLED, note="User cancelled")
                self.checkpoints.record_checkpoint(job_id, JobState.CANCELLED, note="Cancelled")
                raise RuntimeError("Job cancelled by user")
            sm.transition_to(next_state, note=note)
            self.checkpoints.record_checkpoint(job_id, next_state, note=note)

        try:
            # 1. VALIDATING_INPUT
            step_checkpoint(JobState.VALIDATING_INPUT, "Checking PDF properties")
            size_bytes, page_count = inspect_pdf(pdf_path)

            # 2. STARTING_BROWSER
            step_checkpoint(JobState.STARTING_BROWSER, "Launching visible Chromium context")
            page = browser_manager.launch()
            adapter = GeminiPageAdapter(page, self.cfg)
            adapter.navigate()

            # 3. AUTH / READINESS
            if adapter.check_is_auth_required():
                step_checkpoint(JobState.WAITING_FOR_AUTH, "User manual sign-in required in visible browser")
                logger.info("Waiting for user to sign in to Google in visible browser...")
                auth_start = time.time()
                auth_timeout_s = 600  # 10 minutes for manual sign-in
                while time.time() - auth_start < auth_timeout_s:
                    if self._cancel_requested:
                        step_checkpoint(JobState.CANCELLED, "Cancelled during authentication")
                        return self.db.get_job(job_id)
                    if adapter.is_composer_ready():
                        logger.info("Sign-in detected! Gemini chat composer is ready.")
                        break
                    time.sleep(2)
                else:
                    step_checkpoint(JobState.NEEDS_USER_ACTION, "Manual sign-in timed out after 10 minutes.")
                    return self.db.get_job(job_id)

            # Wait for interface readiness
            if not adapter.is_composer_ready():
                step_checkpoint(JobState.WAITING_FOR_USER_READY, "Waiting for Gemini interface readiness")
                ready_start = time.time()
                while time.time() - ready_start < 45:
                    if self._cancel_requested:
                        step_checkpoint(JobState.CANCELLED, "Cancelled during readiness wait")
                        return self.db.get_job(job_id)
                    if adapter.is_composer_ready():
                        break
                    time.sleep(2)
                else:
                    step_checkpoint(JobState.NEEDS_USER_ACTION, "Interface not ready. Please inspect browser.")
                    return self.db.get_job(job_id)

            # 4. UPLOADING
            step_checkpoint(JobState.UPLOADING, f"Uploading {pdf_path.name}")
            upload_success = adapter.upload_pdf(pdf_path)

            # 5. CONFIRMING_ATTACHMENT
            step_checkpoint(JobState.CONFIRMING_ATTACHMENT, "Verifying attachment chip")
            if not upload_success:
                step_checkpoint(
                    JobState.NEEDS_USER_ACTION,
                    "Upload chip not confirmed automatically; user confirmation needed."
                )
                return self.db.get_job(job_id)

            # 6. SUBMITTING
            step_checkpoint(JobState.SUBMITTING, "Sending extraction prompt")
            prompt_text = self.load_prompt_content()
            adapter.submit_prompt(prompt_text)

            # 7. WAITING_FOR_RESPONSE
            step_checkpoint(JobState.WAITING_FOR_RESPONSE, "Waiting for generation completion")
            try:
                completed = adapter.wait_for_completion()
                if not completed:
                    step_checkpoint(
                        JobState.NEEDS_USER_ACTION,
                        "Generation timeout; check if response is complete in browser."
                    )
                    return self.db.get_job(job_id)
            except RuntimeError as re_err:
                if "Usage limit" in str(re_err):
                    step_checkpoint(JobState.PAUSED_USAGE_LIMIT, "Hit Gemini usage/rate limits.")
                    return self.db.get_job(job_id)
                raise

            # 8. CAPTURING_RESPONSE
            step_checkpoint(JobState.CAPTURING_RESPONSE, "Extracting latest response text")
            raw_text = adapter.capture_latest_response()

            # 9. RAW_RESPONSE_SAVED
            raw_path = self.artifacts.save_raw_response(job_id, pdf_path.name, raw_text)
            step_checkpoint(JobState.RAW_RESPONSE_SAVED, f"Saved raw response to {raw_path.name}")
            self.db.update_job_artifacts(job_id, raw_path=str(raw_path))

            # 10. Process raw response offline
            result = self.process_raw_response_offline(job_id, pdf_path.name, raw_text, expected_count)
            return result

        except Exception as e:
            logger.exception(f"Pipeline execution failure on job {job_id}: {e}")
            err_type = type(e).__name__
            self.db.set_job_error(
                job_id=job_id,
                error_code="PIPELINE_ERROR",
                error_message=f"{err_type}: {e}",
                status=JobState.FAILED_PERMANENT,
            )
            browser_manager.close()
            return self.db.get_job(job_id)
        finally:
            # Check terminal state to release resources cleanly
            job = self.db.get_job(job_id)
            if job and job.get("status") in {JobState.COMPLETED.value, JobState.FAILED_PERMANENT.value, JobState.CANCELLED.value}:
                browser_manager.close()

    def process_raw_response_offline(
        self,
        job_id: str,
        source_filename: str,
        raw_text: str,
        expected_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Parses and validates raw response offline without any browser dependency.
        """
        # 1. PARSING_JSON
        self.checkpoints.record_checkpoint(job_id, JobState.PARSING_JSON, "Parsing raw text JSON")
        parsed_data, parse_error = parse_raw_response(raw_text)

        if parse_error or parsed_data is None:
            report = generate_validation_report(
                job_id=job_id,
                schema_valid=False,
                errors=[f"Parse Error: {parse_error}"],
                warnings=[],
                extracted_count=0,
                expected_count=expected_count,
            )
            report_path = self.artifacts.save_validation_report(job_id, source_filename, report)
            self.checkpoints.record_checkpoint(
                job_id,
                JobState.NEEDS_USER_ACTION,
                note=f"Malformed JSON: {parse_error}",
                report_path=report_path,
            )
            return self.db.get_job(job_id)

        # 2. VALIDATING_SCHEMA
        self.checkpoints.record_checkpoint(
            job_id, JobState.VALIDATING_SCHEMA, "Validating canonical schema and completeness"
        )
        schema_ok, schema_errors = validate_json_schema(parsed_data)
        pydantic_ok, pydantic_errors, _ = validate_with_pydantic(parsed_data)
        complete_ok, complete_issues = check_question_completeness(parsed_data, expected_count)
        quality_warnings = audit_question_quality(parsed_data)

        all_errors = schema_errors + pydantic_errors + complete_issues
        is_structurally_valid = schema_ok and pydantic_ok and (len(all_errors) == 0)

        # 3. Save artifacts
        output_path = self.artifacts.save_output_json(job_id, source_filename, parsed_data)
        report = generate_validation_report(
            job_id=job_id,
            schema_valid=is_structurally_valid,
            errors=all_errors,
            warnings=quality_warnings,
            extracted_count=len(parsed_data) if isinstance(parsed_data, list) else 0,
            expected_count=expected_count,
        )
        report_path = self.artifacts.save_validation_report(job_id, source_filename, report)

        self.db.update_job_artifacts(
            job_id,
            output_path=str(output_path),
            report_path=str(report_path),
        )

        # 4. Final state determination
        if not is_structurally_valid:
            self.checkpoints.record_checkpoint(
                job_id,
                JobState.NEEDS_USER_ACTION,
                note=f"Validation failed with {len(all_errors)} errors.",
                output_path=output_path,
                report_path=report_path,
            )
        elif report["content_review_required"]:
            self.checkpoints.record_checkpoint(
                job_id,
                JobState.CONTENT_REVIEW_REQUIRED,
                note=f"Extracted {len(parsed_data)} questions. Content warnings flagged.",
                output_path=output_path,
                report_path=report_path,
            )
        else:
            self.checkpoints.record_checkpoint(
                job_id,
                JobState.COMPLETED,
                note=f"Extracted {len(parsed_data)} questions with full schema compliance.",
                output_path=output_path,
                report_path=report_path,
            )

        return self.db.get_job(job_id)

    def load_prompt_content(self) -> str:
        """Loads default extraction prompt from prompts/extraction.md."""
        prompt_path = self.cfg.default_prompt_path
        if prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        return "Extract all MCQs in bilingual JSON format as specified."

job_manager = JobManager()
