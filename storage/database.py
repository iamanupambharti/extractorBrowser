"""
SQLite database management for ExamForge Browser.
Tracks jobs, state transitions, artifact paths, and error states persistently.
"""
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from core.config import config
from core.state_machine import JobState, TERMINAL_STATES
from core.logging_config import logger

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source_filename TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_size_bytes INTEGER DEFAULT 0,
    source_page_count INTEGER DEFAULT 0,
    status TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    raw_path TEXT,
    output_path TEXT,
    report_path TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    note TEXT,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_transitions_job ON job_transitions(job_id);
"""

class Database:
    """Encapsulates SQLite interactions with thread-safe connections."""
    def __init__(self, db_path: Path = config.db_path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Create tables if they do not exist."""
        with self.get_connection() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

    def create_job(
        self,
        job_id: str,
        source_filename: str,
        source_sha256: str,
        source_size_bytes: int = 0,
        source_page_count: int = 0,
        prompt_version: str = config.prompt_version,
        schema_version: str = config.schema_version,
        initial_status: JobState = JobState.QUEUED,
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, source_filename, source_sha256, source_size_bytes, source_page_count,
                    status, prompt_version, schema_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    source_filename,
                    source_sha256,
                    source_size_bytes,
                    source_page_count,
                    initial_status.value,
                    prompt_version,
                    schema_version,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO job_transitions (job_id, from_state, to_state, timestamp, note)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, None, initial_status.value, now, "Job created"),
            )
            conn.commit()
        return self.get_job(job_id)

    def record_transition(
        self,
        job_id: str,
        from_state: Optional[str],
        to_state: str,
        note: str = ""
    ) -> None:
        now = datetime.utcnow().isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO job_transitions (job_id, from_state, to_state, timestamp, note)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, from_state, to_state, now, note),
            )
            conn.execute(
                """
                UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?
                """,
                (to_state, now, job_id),
            )
            conn.commit()

    def update_job_artifacts(
        self,
        job_id: str,
        raw_path: Optional[str] = None,
        output_path: Optional[str] = None,
        report_path: Optional[str] = None,
    ) -> None:
        now = datetime.utcnow().isoformat()
        updates = []
        params = []
        if raw_path is not None:
            updates.append("raw_path = ?")
            params.append(str(raw_path))
        if output_path is not None:
            updates.append("output_path = ?")
            params.append(str(output_path))
        if report_path is not None:
            updates.append("report_path = ?")
            params.append(str(report_path))
        if not updates:
            return
        updates.append("updated_at = ?")
        params.append(now)
        params.append(job_id)
        
        sql = f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?"
        with self.get_connection() as conn:
            conn.execute(sql, params)
            conn.commit()

    def set_job_error(
        self,
        job_id: str,
        error_code: str,
        error_message: str,
        status: JobState = JobState.FAILED_PERMANENT,
    ) -> None:
        now = datetime.utcnow().isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE jobs SET status = ?, error_code = ?, error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (status.value, error_code, error_message, now, job_id),
            )
            conn.execute(
                """
                INSERT INTO job_transitions (job_id, from_state, to_state, timestamp, note)
                VALUES (?, (SELECT status FROM jobs WHERE id = ?), ?, ?, ?)
                """,
                (job_id, job_id, status.value, now, f"Error: [{error_code}] {error_message}"),
            )
            conn.commit()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def list_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM jobs ORDER BY datetime(created_at) DESC LIMIT ?", (limit,)
            )
            return [dict(row) for row in cur.fetchall()]

    def get_job_transitions(self, job_id: str) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM job_transitions WHERE job_id = ? ORDER BY id ASC", (job_id,)
            )
            return [dict(row) for row in cur.fetchall()]

    def get_active_job(self) -> Optional[Dict[str, Any]]:
        """Return the currently active non-terminal job, if any."""
        terminal_vals = [s.value for s in TERMINAL_STATES]
        placeholders = ",".join(["?"] * len(terminal_vals))
        query = f"SELECT * FROM jobs WHERE status NOT IN ({placeholders}) ORDER BY datetime(created_at) DESC LIMIT 1"
        with self.get_connection() as conn:
            cur = conn.execute(query, terminal_vals)
            row = cur.fetchone()
            return dict(row) if row else None

db = Database()
