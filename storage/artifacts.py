"""
Artifact storage for ExamForge Browser.
Handles atomic file writes, deterministic collision-safe naming, and reading/writing artifacts.
"""
from pathlib import Path
import json
import re
import os
import tempfile
from typing import Any, Dict
from core.config import config
from core.logging_config import logger

def sanitize_slug(name: str, max_length: int = 50) -> str:
    """Sanitize a filename component into a safe slug."""
    # Strip any trailing extension if present
    if "." in name:
        name = name.rsplit(".", 1)[0]
    # Replace non-alphanumeric with underscores
    clean = re.sub(r"[^A-Za-z0-9]", "_", name)
    clean = re.sub(r"_+", "_", clean).strip("_")
    if not clean:
        clean = "document"
    return clean[:max_length]

def get_job_artifact_prefix(job_id: str, source_filename: str) -> str:
    """Generate deterministic prefix: <slug>__<job_id>."""
    slug = sanitize_slug(source_filename)
    return f"{slug}__{job_id}"

def atomic_write_text(target_path: Path, content: str, encoding: str = "utf-8") -> Path:
    """
    Atomically writes text to target_path using a temporary file in the same directory.
    Guarantees no half-written or corrupted artifacts.
    """
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to a temporary file in the same directory to allow atomic os.replace
    temp_dir = target_path.parent
    fd, temp_file_path = tempfile.mkstemp(prefix="tmp_", suffix=".tmp", dir=temp_dir)
    try:
        with open(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        # Atomic replace
        os.replace(temp_file_path, target_path)
    except Exception as e:
        logger.error(f"Failed atomic write to {target_path}: {e}")
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass
        raise
    return target_path

def atomic_write_json(target_path: Path, data: Any, indent: int = 2) -> Path:
    """Atomically writes JSON serializable object to target_path."""
    content = json.dumps(data, ensure_ascii=False, indent=indent)
    return atomic_write_text(target_path, content)

class ArtifactManager:
    """Manages raw responses, output JSON files, and validation reports."""
    def __init__(self, app_config=config):
        self.cfg = app_config
        self.cfg.ensure_directories()

    def get_raw_path(self, job_id: str, source_filename: str) -> Path:
        prefix = get_job_artifact_prefix(job_id, source_filename)
        return self.cfg.raw_dir / f"{prefix}__raw.txt"

    def get_output_path(self, job_id: str, source_filename: str) -> Path:
        prefix = get_job_artifact_prefix(job_id, source_filename)
        return self.cfg.outputs_dir / f"{prefix}__output.json"

    def get_report_path(self, job_id: str, source_filename: str) -> Path:
        prefix = get_job_artifact_prefix(job_id, source_filename)
        return self.cfg.reports_dir / f"{prefix}__validation.json"

    def save_raw_response(self, job_id: str, source_filename: str, raw_text: str) -> Path:
        path = self.get_raw_path(job_id, source_filename)
        atomic_write_text(path, raw_text)
        logger.info(f"Saved raw response artifact to {path}")
        return path

    def save_output_json(self, job_id: str, source_filename: str, json_data: Any) -> Path:
        path = self.get_output_path(job_id, source_filename)
        atomic_write_json(path, json_data)
        logger.info(f"Saved final JSON artifact to {path}")
        return path

    def save_validation_report(self, job_id: str, source_filename: str, report_data: Dict[str, Any]) -> Path:
        path = self.get_report_path(job_id, source_filename)
        atomic_write_json(path, report_data)
        logger.info(f"Saved validation report artifact to {path}")
        return path

    def read_raw_response(self, path: Path) -> str:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def read_output_json(self, path: Path) -> Any:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def read_validation_report(self, path: Path) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

artifacts = ArtifactManager()
