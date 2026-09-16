"""
Configuration and settings management for ExamForge Browser.
"""
from dataclasses import dataclass, field
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

@dataclass
class AppConfig:
    # Directories
    base_dir: Path = BASE_DIR
    data_dir: Path = BASE_DIR / "data"
    inputs_dir: Path = BASE_DIR / "data" / "inputs"
    raw_dir: Path = BASE_DIR / "data" / "raw"
    outputs_dir: Path = BASE_DIR / "data" / "outputs"
    reports_dir: Path = BASE_DIR / "data" / "reports"
    logs_dir: Path = BASE_DIR / "data" / "logs"
    browser_profile_dir: Path = BASE_DIR / "data" / "browser_profile"
    
    # Prompt and schema paths
    prompts_dir: Path = BASE_DIR / "prompts"
    schemas_dir: Path = BASE_DIR / "schemas"
    default_prompt_path: Path = BASE_DIR / "prompts" / "extraction.md"
    default_schema_path: Path = BASE_DIR / "schemas" / "schema_template.json"
    
    # Database
    db_path: Path = BASE_DIR / "data" / "examforge.db"
    
    # Browser Automation Settings
    gemini_url: str = "https://gemini.google.com/app"
    headless: bool = False
    viewport_width: int = 1280
    viewport_height: int = 900
    
    # Timeouts (in seconds)
    page_load_timeout_s: int = 60
    element_wait_timeout_s: int = 25
    generation_timeout_s: int = 300
    upload_timeout_s: int = 60
    
    # Retry and execution policies
    max_retries: int = 2
    retry_delay_s: float = 3.0
    prompt_version: str = "1.0.0"
    schema_version: str = "1.0.0"

    def ensure_directories(self) -> None:
        """Create required runtime folders if they do not exist."""
        for folder in [
            self.data_dir,
            self.inputs_dir,
            self.raw_dir,
            self.outputs_dir,
            self.reports_dir,
            self.logs_dir,
            self.browser_profile_dir,
            self.prompts_dir,
            self.schemas_dir,
        ]:
            folder.mkdir(parents=True, exist_ok=True)

# Global default config instance
config = AppConfig()
config.ensure_directories()
