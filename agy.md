# ExamForge Browser — Implementation Plan & System Architecture

This document provides the end-to-end implementation plan and architectural specification for **ExamForge Browser**, derived from [plan.md](file:///D:/Classroom/Coding/ectractorBrowser/plan.md).

---

## 1. Executive Summary & Objective

**ExamForge Browser** is a local-first, Python-based automation and review platform for extracting bilingual question banks (English/Hindi) from examination PDFs via user-supervised Gemini web interface interactions (`https://gemini.google.com/`).

Key objectives:
- **Data Integrity & Traceability First:** Preserve raw responses immutably before parsing; use atomic writes and collision-safe deterministic filenames.
- **Strict Separation of Concerns:** Browser interactions, job state machine, SQLite storage, JSON/schema validation, and Streamlit UI remain modular.
- **Resilient Automation:** Non-headless Chromium with a dedicated persistent profile (retaining Google login without storing credentials). Explicit readiness, upload confirmation, generation completion detection, and manual review pauses when UI state is ambiguous.
- **Offline Verifiability:** Complete test suite covering parsing, schema validation, quality checks, state machine transitions, naming sanitization, and database checkpointing without needing an active Gemini connection.

---

## 2. Directory Layout & Module Structure

```text
ectractorBrowser/
├── plan.md                       # High-level product specification & source of truth
├── agy.md                        # Implementation plan and architectural roadmap
├── requirements.txt              # Pinned core dependencies
├── .gitignore                    # Git safety rules (protecting profile, data, credentials)
├── README.md                     # Setup instructions and operations guide
├── app.py                        # Streamlit dashboard entrypoint
├── prompts/
│   ├── extraction.md             # Primary bilingual extraction prompt template
│   └── repair.md                 # Narrow schema repair prompt template
├── schemas/
│   └── schema_template.json      # Canonical bilingual question-bank JSON Schema
├── browser/
│   ├── __init__.py
│   ├── selectors.py              # Centralized UI locators with fallback strategies
│   ├── launch.py                 # Persistent Chromium lifecycle management
│   └── gemini_page.py            # Page-level interactions (upload, submit, wait, capture)
├── core/
│   ├── __init__.py
│   ├── config.py                 # System configuration, paths, timeouts, retry limits
│   ├── logging_config.py         # Rotating logger with sensitive data redaction
│   ├── state_machine.py          # State definitions and transition enforcement
│   ├── checkpoint.py             # Atomic checkpointing and crash recovery
│   └── job_manager.py            # Single-active-job orchestrator with pause/resume/cancel
├── validation/
│   ├── __init__.py
│   ├── parse_response.py         # Raw text to JSON extraction & markdown fence handling
│   ├── validate_json.py          # Pydantic & JSON Schema structural validation
│   ├── completeness.py           # Question counting, option alignment, gap detection
│   └── quality_flags.py          # Pedagogical & content quality auditing
├── storage/
│   ├── __init__.py
│   ├── database.py               # SQLite schema, job records, transition logs
│   └── artifacts.py              # Atomic filesystem reads/writes for raw & JSON files
├── data/                         # Local-only ignored directory
│   ├── inputs/
│   ├── raw/
│   ├── outputs/
│   ├── reports/
│   ├── logs/
│   └── browser_profile/
└── tests/
    ├── __init__.py
    ├── conftest.py               # Test fixtures and mock data
    ├── test_parsing.py           # JSON and markdown fence extraction tests
    ├── test_schema.py            # Pydantic & JSON Schema validation tests
    ├── test_state_machine.py     # State transition legality tests
    ├── test_naming.py            # Slug sanitization & atomic file write tests
    ├── test_completeness.py      # Question count & option consistency tests
    └── test_browser_mock.py      # Simulated browser page workflow tests
```

---

## 3. Core Architectural Components

### 3.1 State Machine (`core/state_machine.py`)
Finite state machine tracking valid progression, timestamps, and error codes:
- `QUEUED`
- `VALIDATING_INPUT`
- `STARTING_BROWSER`
- `WAITING_FOR_AUTH`
- `WAITING_FOR_USER_READY`
- `UPLOADING`
- `CONFIRMING_ATTACHMENT`
- `SUBMITTING`
- `WAITING_FOR_RESPONSE`
- `CAPTURING_RESPONSE`
- `RAW_RESPONSE_SAVED`
- `PARSING_JSON`
- `VALIDATING_SCHEMA`
- `CONTENT_REVIEW_REQUIRED`
- `COMPLETED`
- `NEEDS_USER_ACTION`
- `PAUSED_USAGE_LIMIT`
- `FAILED_RETRYABLE`
- `FAILED_PERMANENT`
- `CANCELLED`

### 3.2 Job Lifecycle & Persistence (`core/job_manager.py`, `storage/database.py`, `storage/artifacts.py`)
- Single-active-job constraint enforced at runtime.
- Unique Job ID generation (`job_<hash>_<timestamp>`).
- SHA-256 fingerprinting of input PDFs to prevent duplicate/ambiguous processing.
- Two-phase artifact commit: Write temp file -> flush -> fsync -> atomic rename.
- SQLite job ledger storing: `id`, `source_filename`, `source_sha256`, `status`, `prompt_version`, `schema_version`, `raw_path`, `output_path`, `report_path`, `error_message`, `error_code`, `created_at`, `updated_at`.

### 3.3 Browser Automation & Gemini Interactions (`browser/`)
- Persistent Chromium profile stored in `data/browser_profile/` so login cookies persist across runs.
- `launch.py`: launches browser in visible mode (`headless=False`).
- `selectors.py`: ordered fallback locators (accessible role/aria, placeholder, visible text, scoped CSS).
- `gemini_page.py`:
  1. `check_readiness()`: checks if user is logged in or composer is present.
  2. `upload_pdf(file_path)`: triggers file upload dialog/input and confirms upload chip/attachment visually.
  3. `submit_prompt(prompt_text)`: inputs text into composer, triggers submit, confirms message was posted.
  4. `wait_for_completion(timeout_s)`: monitors stop-generating buttons, idle send buttons, or generation completion indicators.
  5. `capture_latest_response()`: extracts text from latest assistant turn.

### 3.4 Parsing & Canonical Bilingual Question Validation (`validation/`)
- **Canonical Question Format**:
  - `type`: "MCQ"
  - `en`: `{"text": "...", "options": [{"id": "opt1", "text": "..."}]}`
  - `hi`: `{"text": "...", "options": [{"id": "opt1", "text": "..."}]}`
  - `correctOptionId`: matches one of option IDs
  - `subject`, `topic`: non-empty strings
  - `has_image`: boolean
  - `explanation`: `{"en": "...", "hi": "..."}`
- `parse_response.py`: removes Markdown JSON codeblock fences (` ```json `), handles leading/trailing notes, preserves raw text.
- `validate_json.py`: validates against `schemas/schema_template.json` and Pydantic models.
- `completeness.py` & `quality_flags.py`: verifies option ID matching across English and Hindi, flags suspicious translations, missing answers, or math syntax discrepancies.

### 3.5 Streamlit User Interface (`app.py`)
- **Dashboard**:
  - File picker & PDF inspection (page count, file size, SHA-256).
  - One-click Job Execution (Start, Pause, Resume, Cancel).
  - Status banner, live state machine badge, and next recommended action.
  - Quick action buttons to open output and report files.
- **Job Explorer**:
  - Interactive table of all historical and active jobs.
  - Detailed state transition timeline with timestamped audits.
- **Review & Inspection**:
  - Side-by-side English/Hindi question card viewer with answer key validation and explanation breakdown.
  - Raw Gemini response viewer vs. parsed JSON viewer.
  - Validation report inspector showing errors and quality warnings.
- **Settings & Profile Management**:
  - Timeout configurations, retry thresholds, custom Gemini prompt inspection.
  - Browser profile reset utility with confirmation guardrail.

---

## 4. Implementation Phases

- [x] **Phase 1: Environment & Project Foundation**
  - Pin `requirements.txt` (Playwright, PyMuPDF, Pydantic, jsonschema, Streamlit, pytest).
  - Configure `.gitignore` and `README.md`.
  - Establish `prompts/` and `schemas/schema_template.json`.
- [x] **Phase 2: Storage & Core State Management**
  - Implement SQLite database layer (`storage/database.py`).
  - Implement atomic artifact read/write system (`storage/artifacts.py`).
  - Build State Machine and transition validator (`core/state_machine.py`).
  - Build Checkpoint recovery engine (`core/checkpoint.py`).
  - Build Job Manager (`core/job_manager.py`).
- [x] **Phase 3: Parsing, Validation & Content Quality**
  - Implement raw text JSON extractor (`validation/parse_response.py`).
  - Implement JSON schema & Pydantic validators (`validation/validate_json.py`).
  - Implement completeness & option matching checks (`validation/completeness.py`).
  - Implement pedagogical quality flags (`validation/quality_flags.py`).
- [x] **Phase 4: Browser Automation Layer**
  - Implement selector catalog with resilient fallbacks (`browser/selectors.py`).
  - Implement browser lifecycle manager (`browser/launch.py`).
  - Implement Gemini page automation adapter (`browser/gemini_page.py`).
- [x] **Phase 5: User Interface (Streamlit Dashboard)**
  - Implement full-featured `app.py` with multi-tab interface (Dashboard, Job Ledger, Question Review, System Settings).
- [x] **Phase 6: Testing & Verification**
  - Unit tests for parsing, schema validation, state machine, naming sanitization, completeness checks, and mock browser automation.
  - Run pytest suite and ensure 100% test pass rate.
