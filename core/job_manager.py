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
from typing import Optional, Dict, Any, Tuple, List
import fitz  # PyMuPDF

from core.config import config
from core.state_machine import JobState, StateMachine, InvalidStateTransitionError
from core.checkpoint import checkpoint_manager, CheckpointManager
from core.logging_config import logger
from core.pdf_splitter import split_pdf, PDFChunk
from storage.database import db
from storage.artifacts import artifacts
from validation.parse_response import parse_raw_response
from validation.validate_json import validate_json_schema, validate_with_pydantic
from validation.completeness import check_question_completeness
from validation.quality_flags import audit_question_quality, generate_validation_report
from validation.merge_chunks import merge_question_chunks
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

    def auto_approve_and_resume(
        self,
        job_id: str,
        pdf_path: Optional[Path] = None,
        expected_count: Optional[int] = None,
    ) -> None:
        """Resumes a job in NEEDS_USER_ACTION by auto-approving user permission or reprocessing saved raw response."""
        job = self.db.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found.")

        # If raw response was already saved, reprocess offline immediately with auto-repair!
        raw_path_str = job.get("raw_path")
        if raw_path_str and Path(raw_path_str).exists():
            logger.info(f"Raw response exists for job {job_id}. Reprocessing offline with auto-repair...")
            with open(raw_path_str, "r", encoding="utf-8") as f:
                raw_text = f.read()
            self._active_thread = threading.Thread(
                target=self.process_raw_response_offline,
                args=(job_id, job["source_filename"], raw_text, expected_count),
                daemon=True,
                name=f"Worker-Offline-{job_id}",
            )
            self._active_thread.start()
            return

        target_pdf = pdf_path
        if not target_pdf or not target_pdf.exists():
            candidate = self.cfg.inputs_dir / job["source_filename"]
            if candidate.exists():
                target_pdf = candidate

        if not target_pdf or not target_pdf.exists():
            raise FileNotFoundError(f"Source PDF for job {job_id} not found.")

        self._cancel_requested = False
        self._pause_requested = False
        self._active_thread = threading.Thread(
            target=self.run_pipeline,
            args=(job_id, target_pdf, expected_count, False, "SUBMITTING"),
            daemon=True,
            name=f"Worker-Resume-{job_id}",
        )
        self._active_thread.start()
        logger.info(f"Started background resume worker thread for job {job_id}")

    def run_api_pipeline(
        self,
        job_id: str,
        pdf_path: Path,
        expected_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Executes extraction directly via the official Gemini API.
        Completely eliminates browser automation, bot detection, profile locks, and UI changes.
        """
        self._cancel_requested = False
        self._pause_requested = False
        self.current_job_id = job_id

        job_rec = self.db.get_job(job_id)
        current_status = JobState(job_rec["status"]) if job_rec and job_rec.get("status") else JobState.QUEUED
        sm = StateMachine(current_status)

        def step_checkpoint(next_state: JobState, note: str = ""):
            if self._cancel_requested:
                sm.transition_to(JobState.CANCELLED, note="User cancelled")
                self.checkpoints.record_checkpoint(job_id, JobState.CANCELLED, note="Cancelled")
                raise RuntimeError("Job cancelled by user")
            sm.transition_to(next_state, note=note)
            self.checkpoints.record_checkpoint(job_id, next_state, note=note)

        try:
            # 1. SUBMITTING
            model_name = getattr(self.cfg, "gemini_model", "gemini-2.5-flash")
            step_checkpoint(JobState.SUBMITTING, f"Sending PDF directly to Gemini API ({model_name})")
            prompt_text = self.load_prompt_content()

            # 2. WAITING_FOR_RESPONSE
            step_checkpoint(JobState.WAITING_FOR_RESPONSE, f"Gemini API processing extraction with {model_name}...")
            from core.gemini_api_engine import gemini_api_engine
            raw_text = gemini_api_engine.extract_from_pdf(pdf_path, prompt_text)

            # 3. CAPTURING_RESPONSE
            step_checkpoint(JobState.CAPTURING_RESPONSE, f"Captured API response ({len(raw_text)} chars)")

            # 4. RAW_RESPONSE_SAVED
            raw_path = self.artifacts.save_raw_response(job_id, pdf_path.name, raw_text)
            step_checkpoint(JobState.RAW_RESPONSE_SAVED, f"Saved raw response to {raw_path.name}")
            self.db.update_job_artifacts(job_id, raw_path=str(raw_path))

            # 5. Process raw response offline (PARSING_JSON -> VALIDATING_SCHEMA -> COMPLETED)
            result = self.process_raw_response_offline(job_id, pdf_path.name, raw_text, expected_count)
            return result

        except Exception as e:
            logger.exception(f"API pipeline execution failure on job {job_id}: {e}")
            err_type = type(e).__name__
            self.db.set_job_error(
                job_id=job_id,
                error_code="API_ERROR",
                error_message=f"{err_type}: {e}",
                status=JobState.FAILED_PERMANENT,
            )
            return self.db.get_job(job_id)

    def run_pipeline(
        self,
        job_id: str,
        pdf_path: Path,
        expected_count: Optional[int] = None,
        manual_auth_confirm: bool = False,
        resume_from_step: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes the end-to-end browser extraction and validation pipeline.
        Runs entirely on the caller's thread to preserve Playwright connection integrity.
        """
        self._cancel_requested = False
        self._pause_requested = False
        self.current_job_id = job_id
        
        job_rec = self.db.get_job(job_id)
        current_status = JobState(job_rec["status"]) if job_rec and job_rec.get("status") else JobState.QUEUED
        sm = StateMachine(current_status)

        def step_checkpoint(next_state: JobState, note: str = ""):
            if self._cancel_requested:
                sm.transition_to(JobState.CANCELLED, note="User cancelled")
                self.checkpoints.record_checkpoint(job_id, JobState.CANCELLED, note="Cancelled")
                raise RuntimeError("Job cancelled by user")
            sm.transition_to(next_state, note=note)
            self.checkpoints.record_checkpoint(job_id, next_state, note=note)

        try:
            # 1. VALIDATING_INPUT
            page_count = 1
            if resume_from_step != "SUBMITTING":
                step_checkpoint(JobState.VALIDATING_INPUT, "Checking PDF properties")
                size_bytes, page_count = inspect_pdf(pdf_path)

            # If engine_type is "api", execute via direct Gemini API engine
            if getattr(self.cfg, "engine_type", "api") == "api":
                logger.info(f"Engine type is 'api'. Running direct Gemini API pipeline for {pdf_path.name}")
                return self.run_api_pipeline(job_id, pdf_path, expected_count)

            # Check if PDF exceeds threshold and should run the chunked pipeline (disabled by default)
            enable_splitting = getattr(self.cfg, "enable_pdf_splitting", False)
            split_threshold = getattr(self.cfg, "pdf_split_threshold_pages", 2)
            if enable_splitting and page_count > split_threshold and resume_from_step != "SUBMITTING":
                logger.info(f"PDF page count ({page_count}) > threshold ({split_threshold}). Triggering chunked pipeline.")
                return self.run_chunked_pipeline(job_id, pdf_path, page_count, expected_count)

            # 2. STARTING_BROWSER
            if current_status not in {JobState.SUBMITTING, JobState.CONFIRMING_ATTACHMENT, JobState.NEEDS_USER_ACTION} or not browser_manager.is_healthy():
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

            # 4. UPLOADING & 5. CONFIRMING_ATTACHMENT
            if resume_from_step != "SUBMITTING":
                step_checkpoint(JobState.UPLOADING, f"Uploading {pdf_path.name}")
                upload_success = adapter.upload_pdf(pdf_path)

                step_checkpoint(JobState.CONFIRMING_ATTACHMENT, "Verifying attachment chip")
                if not upload_success:
                    auto_approve = getattr(self.cfg, "auto_approve_permission", True)
                    if auto_approve:
                        logger.info("Upload chip not confirmed automatically; auto-approving user permission and continuing.")
                    else:
                        step_checkpoint(
                            JobState.NEEDS_USER_ACTION,
                            "Upload chip not confirmed automatically; user confirmation needed."
                        )
                        return self.db.get_job(job_id)

            # 6. SUBMITTING
            already_generated = False
            if resume_from_step == "SUBMITTING":
                try:
                    existing_text = adapter.capture_latest_response()
                    if existing_text and len(existing_text) > 100:
                        logger.info(f"Existing model response found on page ({len(existing_text)} chars). Skipping re-submission.")
                        already_generated = True
                except Exception:
                    pass

            if not already_generated:
                step_checkpoint(JobState.SUBMITTING, "Sending extraction prompt")
                prompt_text = self.load_prompt_content()
                adapter.submit_prompt(prompt_text)

                # 7. WAITING_FOR_RESPONSE
                step_checkpoint(JobState.WAITING_FOR_RESPONSE, "Waiting for generation completion")
                try:
                    completed = adapter.wait_for_completion()
                    if not completed:
                        # Attempt to capture whatever has been rendered
                        try:
                            raw_check = adapter.capture_latest_response()
                            if raw_check and len(raw_check) > 100:
                                logger.info(f"Recovered response ({len(raw_check)} chars) despite completion warning.")
                                completed = True
                        except Exception:
                            pass

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

    def run_chunked_pipeline(
        self,
        job_id: str,
        pdf_path: Path,
        total_pages: int,
        expected_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Executes chunked extraction for multi-page documents:
        1. Splits the document into 2-3 page chunks.
        2. Iterates over chunks in Gemini browser.
        3. Captures raw responses per chunk.
        4. Merges and deduplicates questions into a single consolidated JSON.
        5. Saves unified artifacts and completes the job.
        """
        chunk_size = getattr(self.cfg, "pdf_chunk_size_pages", 3)
        job_chunks_dir = getattr(self.cfg, "chunks_dir", self.cfg.data_dir / "chunks") / job_id
        job_chunks_dir.mkdir(parents=True, exist_ok=True)

        chunks: List[PDFChunk] = split_pdf(
            input_path=pdf_path,
            output_dir=job_chunks_dir,
            chunk_size=chunk_size,
            min_pages_to_split=getattr(self.cfg, "pdf_split_threshold_pages", 2),
        )

        total_chunks = len(chunks)
        logger.info(f"Starting chunked pipeline for job {job_id}: {total_chunks} chunks to process.")

        parsed_chunks: List[Dict[str, Any]] = []
        raw_texts: List[str] = []

        try:
            # Launch browser once for all chunks
            self.checkpoints.record_checkpoint(
                job_id,
                JobState.STARTING_BROWSER,
                note=f"Launching browser for {total_chunks} chunks (Pages 1-{total_pages})"
            )
            page = browser_manager.launch()
            adapter = GeminiPageAdapter(page, self.cfg)
            adapter.navigate()

            # Sign-in verification if needed
            if adapter.check_is_auth_required():
                self.checkpoints.record_checkpoint(
                    job_id, JobState.WAITING_FOR_AUTH, "User manual sign-in required in browser"
                )
                auth_start = time.time()
                while time.time() - auth_start < 600:
                    if self._cancel_requested:
                        self.checkpoints.record_checkpoint(job_id, JobState.CANCELLED, "Cancelled")
                        return self.db.get_job(job_id)
                    if adapter.is_composer_ready():
                        break
                    time.sleep(2)

            prompt_text = self.load_prompt_content()

            for chunk_idx, chunk in enumerate(chunks):
                if self._cancel_requested:
                    self.checkpoints.record_checkpoint(job_id, JobState.CANCELLED, "Cancelled by user")
                    return self.db.get_job(job_id)

                progress_desc = f"Chunk {chunk.chunk_index}/{total_chunks} (Pages {chunk.start_page}-{chunk.end_page})"
                logger.info(f"Processing {progress_desc}...")

                # Wait for composer readiness
                ready_start = time.time()
                while time.time() - ready_start < 45:
                    if adapter.is_composer_ready():
                        break
                    time.sleep(1)

                # Upload chunk
                self.checkpoints.record_checkpoint(
                    job_id,
                    JobState.UPLOADING,
                    note=f"Uploading {progress_desc}"
                )
                upload_ok = adapter.upload_pdf(chunk.chunk_path)
                self.checkpoints.record_checkpoint(
                    job_id,
                    JobState.CONFIRMING_ATTACHMENT,
                    note=f"Attached {progress_desc}"
                )

                # Submit Prompt
                self.checkpoints.record_checkpoint(
                    job_id,
                    JobState.SUBMITTING,
                    note=f"Submitted prompt for {progress_desc}"
                )
                adapter.submit_prompt(prompt_text)

                # Wait for generation
                self.checkpoints.record_checkpoint(
                    job_id,
                    JobState.WAITING_FOR_RESPONSE,
                    note=f"Waiting response for {progress_desc}"
                )
                completed = adapter.wait_for_completion()
                if not completed:
                    logger.warning(f"Generation timeout on {progress_desc}; attempting capture.")

                # Capture response
                self.checkpoints.record_checkpoint(
                    job_id,
                    JobState.CAPTURING_RESPONSE,
                    note=f"Capturing response for {progress_desc}"
                )
                chunk_raw = adapter.capture_latest_response()
                raw_texts.append(f"--- CHUNK {chunk.chunk_index}/{total_chunks} (Pages {chunk.start_page}-{chunk.end_page}) ---\n{chunk_raw}")

                # Parse chunk JSON
                chunk_data, chunk_err = parse_raw_response(chunk_raw)
                if chunk_data:
                    # In case LLM returned raw array instead of dict
                    if isinstance(chunk_data, list):
                        chunk_dict = {"questions": chunk_data, "metadata": {}}
                    else:
                        chunk_dict = chunk_data
                    parsed_chunks.append(chunk_dict)
                    logger.info(f"Successfully extracted {len(chunk_dict.get('questions', []))} questions from {progress_desc}")
                else:
                    logger.warning(f"Could not parse valid JSON from {progress_desc}: {chunk_err}")

                # Clean up temporary chunk file after processing
                try:
                    if chunk.chunk_path.exists() and chunk.chunk_path != pdf_path:
                        chunk.chunk_path.unlink()
                except Exception:
                    pass

                # Short delay between chunks for browser stability
                time.sleep(2)

            # Consolidate raw text artifact
            full_raw_text = "\n\n".join(raw_texts)
            raw_path = self.artifacts.save_raw_response(job_id, pdf_path.name, full_raw_text)
            self.checkpoints.record_checkpoint(
                job_id, JobState.RAW_RESPONSE_SAVED, f"Saved raw responses from all {total_chunks} chunks"
            )
            self.db.update_job_artifacts(job_id, raw_path=str(raw_path))

            # Merge all chunks
            self.checkpoints.record_checkpoint(
                job_id, JobState.PARSING_JSON, f"Merging questions across {len(parsed_chunks)} chunks"
            )
            merged_result = merge_question_chunks(parsed_chunks)
            merged_questions = merged_result.get("questions", [])

            # Validate merged schema and quality
            self.checkpoints.record_checkpoint(
                job_id, JobState.VALIDATING_SCHEMA, f"Validating {len(merged_questions)} merged questions"
            )
            schema_ok, schema_errors = validate_json_schema(merged_result)
            pydantic_ok, pydantic_errors, _ = validate_with_pydantic(merged_questions)
            complete_ok, complete_issues = check_question_completeness(merged_questions, expected_count)
            quality_warnings = audit_question_quality(merged_questions)

            all_errors = schema_errors + pydantic_errors + complete_issues
            is_structurally_valid = len(merged_questions) > 0 and len(schema_errors) == 0

            # Save final unified artifacts
            output_path = self.artifacts.save_output_json(job_id, pdf_path.name, merged_result)
            report = generate_validation_report(
                job_id=job_id,
                schema_valid=is_structurally_valid,
                errors=all_errors,
                warnings=quality_warnings,
                extracted_count=len(merged_questions),
                expected_count=expected_count,
            )
            report_path = self.artifacts.save_validation_report(job_id, pdf_path.name, report)

            self.db.update_job_artifacts(
                job_id,
                output_path=str(output_path),
                report_path=str(report_path),
            )

            if len(merged_questions) == 0:
                self.checkpoints.record_checkpoint(
                    job_id,
                    JobState.NEEDS_USER_ACTION,
                    note="Zero questions could be parsed across chunks.",
                    output_path=output_path,
                    report_path=report_path,
                )
            else:
                note_msg = f"Extracted {len(merged_questions)} questions across {total_chunks} chunks with full schema compliance."
                if quality_warnings:
                    note_msg += f" ({len(quality_warnings)} content quality notices)."
                self.checkpoints.record_checkpoint(
                    job_id,
                    JobState.COMPLETED,
                    note=note_msg,
                    output_path=output_path,
                    report_path=report_path,
                )

            return self.db.get_job(job_id)

        except Exception as e:
            logger.exception(f"Chunked pipeline execution failure on job {job_id}: {e}")
            err_type = type(e).__name__
            self.db.set_job_error(
                job_id=job_id,
                error_code="PIPELINE_CHUNK_ERROR",
                error_message=f"{err_type}: {e}",
                status=JobState.FAILED_PERMANENT,
            )
            browser_manager.close()
            return self.db.get_job(job_id)
        finally:
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
        else:
            note_msg = f"Extracted {len(parsed_data)} questions with full schema compliance."
            if quality_warnings:
                note_msg += f" ({len(quality_warnings)} content quality notices)."
            self.checkpoints.record_checkpoint(
                job_id,
                JobState.COMPLETED,
                note=note_msg,
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
