# ExamForge Browser

**ExamForge Browser** is a local-first automation and quality verification platform designed to extract bilingual question banks (English and Hindi) from examination PDFs using user-supervised Gemini web interface interactions (`https://gemini.google.com/`).

---

## 🌟 Key Features

- **Visible Browser Automation:** Uses Playwright Chromium with a dedicated persistent profile (`data/browser_profile/`). The user signs in once manually; session cookies persist without storing Google passwords in code or config.
- **Strict Data Integrity:** Raw assistant responses are stored immutably in `data/raw/` before any parsing or transformation occurs.
- **Two-Tier Validation:**
  - **Structural Validation:** JSON Schema (Draft-07) and Pydantic models verify the canonical bilingual schema (`type`, `en`, `hi`, `correctOptionId`, `explanation`, `subject`, `topic`, `has_image`).
  - **Content Quality Checks:** Validates option ID consistency across English and Hindi, flags missing explanations, detect unbalanced math delimiters, and checks question counts.
- **Persistent State Machine & Checkpoints:** SQLite-backed audit trails (`data/examforge.db`) record every state transition. Resumption prevents accidental duplicate submissions.
- **Interactive Streamlit Dashboard:** Multi-tab local dashboard (`app.py`) for launching extractions, tracking job lifecycles, reviewing bilingual cards, and configuring timeouts.

---

## 🏗️ Architecture & Directory Layout

```text
ectractorBrowser/
├── plan.md                       # Comprehensive project specification & source of truth
├── agy.md                        # Phased implementation plan
├── requirements.txt              # Core pinned dependencies
├── .gitignore                    # Git safety rules (excluding profile and data)
├── README.md                     # Documentation
├── app.py                        # Streamlit web dashboard
├── prompts/
│   ├── extraction.md             # Primary bilingual extraction prompt
│   └── repair.md                 # Fallback JSON repair prompt
├── schemas/
│   └── schema_template.json      # Canonical bilingual question schema
├── browser/
│   ├── selectors.py              # Prioritized locator chains
│   ├── launch.py                 # Persistent Chromium lifecycle manager
│   └── gemini_page.py            # Page actions (upload, prompt, wait, capture)
├── core/
│   ├── config.py                 # Configuration and runtime directories
│   ├── logging_config.py         # Structured, redacting rotating logger
│   ├── state_machine.py          # State transitions and legal jumps
│   ├── checkpoint.py             # Atomic state checkpointing and recovery
│   └── job_manager.py            # Orchestrator enforcing single-active-job
├── validation/
│   ├── parse_response.py         # Markdown fence removal and JSON extractor
│   ├── validate_json.py          # Pydantic & JSON Schema validators
│   ├── completeness.py           # Option matching and question counting
│   └── quality_flags.py          # Pedagogical audit flags and report builder
├── storage/
│   ├── database.py               # SQLite database client
│   └── artifacts.py              # Atomic file writer and slug sanitizer
├── data/                         # Local-only runtime data directory
│   ├── inputs/                   # Staged PDFs
│   ├── raw/                      # Immutable raw Gemini responses (.txt)
│   ├── outputs/                  # Validated JSON question banks (.json)
│   ├── reports/                  # Validation reports (.json)
│   ├── logs/                     # Rotating execution logs (.log)
│   └── browser_profile/          # Dedicated Chromium user data directory
└── tests/                        # Offline unit test suite
    ├── conftest.py
    ├── test_parsing.py
    ├── test_schema.py
    ├── test_state_machine.py
    ├── test_naming.py
    ├── test_completeness.py
    └── test_checkpoint.py
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **OS:** Windows 11 (or modern Linux/macOS)
- **Python:** 3.11 recommended

### 2. Installation
```powershell
# Clone or navigate to the repository
cd D:\Classroom\Coding\ectractorBrowser

# Install dependencies
py -3.11 -m pip install -r requirements.txt

# Install Playwright Chromium browser binary
py -3.11 -m playwright install chromium
```

### 3. Running Offline Unit Tests
Run the offline test suite to ensure schema validation, parsing, and state machine integrity:
```powershell
py -3.11 -m pytest tests -v
```

### 4. Launching the Streamlit Dashboard
```powershell
py -3.11 -m streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## 🔄 Workflow Walkthrough

1. **Upload / Select PDF:** On the **Dashboard**, choose an exam PDF. The system inspects readability, page count, and file SHA-256 hash.
2. **Start Extraction:** Click **Start Extraction Job**. Chromium opens visibly.
3. **Sign In (First Run Only):** If Gemini requests login, sign in manually in the visible browser window. Session cookies will persist in `data/browser_profile/` for subsequent runs.
4. **Automated Upload & Submission:** The browser adapter attaches the PDF, verifies the attachment chip, submits the extraction prompt, and monitors the generation status.
5. **Raw Response Capture:** The latest completed response is captured and immediately saved to `data/raw/<slug>__<job_id>__raw.txt`.
6. **Validation & Review:** The parser extracts JSON, runs Pydantic and JSON Schema checks, performs bilingual option alignment, and saves the final JSON to `data/outputs/`. Inspect questions and quality flags in the **Question Review** tab.
7. **Offline Reprocessing:** If an output needed schema repair, click **Reprocess Raw Response Offline** from the **Job Ledger** tab without re-uploading to Gemini.

---

## 🛡️ Security & Privacy

- Dedicated browser profile is isolated from your personal browser.
- Passwords and Google credentials are never handled or logged by the application.
- All logs filter and redact potential keys, tokens, and cookies.
- Real PDF documents, raw responses, and browser profile data are ignored in `.gitignore`.
