"""
Integration tests for JobManager offline flow with dynamic test PDF.
"""
from pathlib import Path
import fitz
import json
import pytest
from core.job_manager import JobManager, inspect_pdf, calculate_sha256
from core.state_machine import JobState
from storage.database import Database
from storage.artifacts import ArtifactManager

def create_dummy_pdf(target_path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Question 1: What is the unit of force? (A) Newton (B) Joule")
    doc.save(target_path)
    doc.close()
    return target_path

def test_inspect_and_hash_pdf(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    create_dummy_pdf(pdf_path)

    size, pages = inspect_pdf(pdf_path)
    assert pages == 1
    assert size > 0

    sha = calculate_sha256(pdf_path)
    assert len(sha) == 64

def test_full_offline_job_processing(tmp_path, sample_raw_fenced_response):
    pdf_path = tmp_path / "mock_exam.pdf"
    create_dummy_pdf(pdf_path)

    db_path = tmp_path / "test_lifecycle.db"
    db_inst = Database(db_path)
    art_inst = ArtifactManager()
    jm = JobManager(database=db_inst, artifact_mgr=art_inst)

    # 1. Create Job
    job = jm.create_job(pdf_path, expected_count=1)
    assert job["id"].startswith("job_")
    assert job["status"] == JobState.QUEUED.value

    # 2. Process raw response offline
    completed_job = jm.process_raw_response_offline(
        job["id"],
        pdf_path.name,
        sample_raw_fenced_response,
        expected_count=1,
    )

    # Check status and artifacts
    assert completed_job["status"] in {
        JobState.COMPLETED.value,
        JobState.CONTENT_REVIEW_REQUIRED.value,
    }
    assert completed_job["output_path"] is not None
    assert Path(completed_job["output_path"]).exists()

    with open(completed_job["output_path"], "r", encoding="utf-8") as f:
        output_data = json.load(f)
    assert len(output_data) == 1
    assert output_data[0]["type"] == "MCQ"
