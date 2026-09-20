"""
Unit tests for safe slug generation, deterministic artifact prefixing, and atomic writes.
"""
from pathlib import Path
import json
import pytest
from storage.artifacts import sanitize_slug, get_job_artifact_prefix, atomic_write_text, atomic_write_json

def test_sanitize_slug_removes_unsafe_chars():
    assert sanitize_slug("JTET 2016 (Paper-1) [Math].pdf") == "JTET_2016_Paper_1_Math"
    assert sanitize_slug("...///unsafe///file.pdf") == "unsafe_file"
    assert sanitize_slug("") == "document"

def test_deterministic_artifact_prefix():
    prefix = get_job_artifact_prefix("job_a1b2_123456", "Science Exam.pdf")
    assert prefix == "Science_Exam__job_a1b2_123456"

def test_atomic_write_text(tmp_path):
    target = tmp_path / "subdir" / "test_file.txt"
    written = atomic_write_text(target, "Hello world!")
    assert written.exists()
    assert written.read_text(encoding="utf-8") == "Hello world!"

def test_atomic_write_json(tmp_path):
    target = tmp_path / "test.json"
    data = {"status": "ok", "count": 42}
    atomic_write_json(target, data)
    assert target.exists()
    with open(target, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded == data
