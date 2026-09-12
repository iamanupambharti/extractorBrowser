# ExamForge Browser-First Automation — Project Plan

**Document status:** Implementation specification / source of truth for the first release  
**Project name:** ExamForge Browser  
**Target platform:** Windows 11, local single-user application  
**Primary language:** Python  
**Primary interface:** Streamlit dashboard (after the browser proof of concept succeeds)  
**Browser automation:** Playwright with Chromium, visible browser, dedicated persistent profile  
**Primary AI interface:** Gemini website at `https://gemini.google.com/` through ordinary browser interactions  
**Primary output:** Validated bilingual question-bank JSON compatible with the existing ExamForge schema  
**Initial execution mode:** One active browser job at a time; user-supervised setup and recovery

> **Important reliability statement:** This plan is designed to reduce mistakes through explicit requirements, checkpoints, validation, testing, and manual recovery. It cannot guarantee that a third-party website, AI-generated content, OCR, or browser automation will never fail. The implementation must detect uncertainty and report it rather than silently claim success.

---

## 1. Project purpose

ExamForge Browser is a new, isolated project that automates the repetitive browser workflow a person normally performs in Gemini:

1. Select an examination PDF.
2. Open Gemini in a browser using a user-authenticated session.
3. Upload the PDF through the visible website interface.
4. submit a carefully versioned extraction prompt and schema.
5. Wait for the response to finish.
6. Capture the visible response.
7. Save the unmodified raw response before parsing it.
8. Parse and validate the result against the required JSON contract.
9. Save valid output and job metadata to disk.
10. Pause and request user intervention when the site, response, account, or output is uncertain.

The purpose is not simply to automate mouse clicks. The goal is to make the browser-based workflow traceable, recoverable, testable, and useful for creating a question bank.

### 1.1 Relationship to the existing ExamForge AI project

The existing ExamForge AI project already has a target bilingual question schema, PDF processing experience, checkpointing concepts, and JSON validation requirements. This new project must be created in a separate repository/folder so experiments cannot damage the existing working project.

Reuse the existing schema as the source contract. Do not silently redesign field names or change the expected output format. If a schema change becomes necessary, document it, version it, and obtain approval before implementation.

### 1.2 Primary problem being tested

The main hypothesis is that a browser-driven Gemini workflow can complete some of the same extraction work currently done through API calls, while fitting the user's preferred workflow. This is a hypothesis, not a guaranteed quota or speed improvement.

The browser project must measure:

- Total time per document and per page/batch.
- Number of completed and incomplete questions.
- JSON/schema validation failures.
- Number of manual interventions.
- Number of retries and failure categories.
- Approximate throughput across representative PDFs.

It must not describe website automation as unlimited, guaranteed faster, or a way to bypass usage restrictions. Gemini Apps has its own limits and policies, which may change. Respect applicable terms, usage limits, login challenges, and access controls.

---

## 2. Goals and non-goals

### 2.1 Goals for the first usable release

- Open Gemini in a dedicated, visible Chromium profile.
- Allow the user to authenticate manually when needed.
- Let the user select one local PDF.
- Submit an extraction prompt and schema through visible browser controls.
- Detect obvious upload or submission failures.
- Wait for generation completion with a bounded timeout.
- Capture the latest completed response from the rendered conversation.
- Preserve the raw response exactly as captured before attempting repairs.
- Parse JSON and validate the result against the configured schema.
- Save outputs using deterministic, collision-safe filenames.
- Maintain a persistent job record and recover from application restarts.
- Distinguish structural validity from factual/content verification.
- Provide actionable errors and a manual recovery path.
- Produce logs that help diagnose failures without recording secrets.
- Run a repeatable test suite for core logic.

### 2.2 Explicit non-goals for version 1

- Bypassing Gemini limits, CAPTCHA, authentication checks, or other access controls.
- Reverse-engineering private endpoints or relying on undocumented internal APIs.
- Automating account creation or login credentials.
- Running many simultaneous Gemini browser sessions.
- Guaranteeing perfect extraction, correct answer keys, or complete bilingual translation.
- Silently guessing missing answers or reconstructing unreadable source content as fact.
- Automatically publishing the output to a production question bank.
- Building a multi-agent system or adding autonomous loops before the basic workflow is reliable.
- Replacing the existing ExamForge AI application.
- Treating successful JSON parsing as proof that the educational content is correct.
- Sending PDFs to a second provider or local model in the first browser-only milestone.

---

## 3. Users, environment, and constraints

### 3.1 Intended user

One user operating the application locally. The first release is not a multi-user web service.

### 3.2 Target machine

- Operating system: Windows 11.
- CPU: Intel Core i7-14650HX.
- GPU: NVIDIA GeForce RTX 4060 Laptop GPU with 8 GB VRAM.
- RAM: 16 GB.
- Browser automation does not require the GPU for browser control; local OCR/model inference is not part of the initial scope.
- Internet access is required for Gemini website use.

### 3.3 Runtime expectations

- Python 3.11 is the initial recommended baseline, provided all pinned dependencies support it.
- Use a project-specific virtual environment.
- Use a visible Chromium browser managed by Playwright.
- Keep the browser profile separate from the user's everyday browser profile.
- The application must not require administrator privileges for normal operation unless a dependency installation explicitly requires them.

### 3.4 Third-party dependency

The project depends on the current Gemini web interface. Website UI changes can break locators, uploads, or response capture. The implementation must make selectors easy to inspect/update and must fail visibly rather than falsely report success.

---

## 4. Functional requirements

Each requirement has an identifier so it can be tested and marked complete.

### FR-001 — Project isolation

The project must live in a new folder/repository, separate from the existing ExamForge AI project. It must not modify existing source files or overwrite existing outputs.

**Acceptance:** Running the new project has no write operations outside its configured project/data paths except browser activity and explicitly selected input/output locations.

### FR-002 — PDF selection

The user must be able to select a local PDF through the UI or a command-line prototype. The system must validate that the file exists, is readable, has a `.pdf` extension, and is not empty.

**Acceptance:** Invalid paths, unsupported files, and unreadable PDFs produce a clear error before opening a Gemini job.

### FR-003 — Job identity

Each job must receive a unique ID. The job record must include source path, source SHA-256 hash, creation time, status, prompt version, schema version, and output paths.

**Acceptance:** Two files with the same filename but different contents cannot be mistaken for the same input.

### FR-004 — Browser launch

The application must launch a visible Chromium instance with a dedicated persistent Playwright profile and navigate to Gemini.

**Acceptance:** The user can see the browser and manually authenticate if required. The application never reads, exports, or copies the user's everyday Chrome profile or cookies.

### FR-005 — Authentication handling

If Gemini requires login, the job must pause for manual sign-in. It must not request the user's password in the Streamlit app, store credentials, automate CAPTCHA solving, or bypass security challenges.

**Acceptance:** The application resumes only after the user confirms the page is ready and the expected interface is visible.

### FR-006 — Page readiness

Before uploading or submitting, the browser adapter must confirm that the expected Gemini page is loaded and an input composer is available. It must not rely solely on a fixed sleep.

**Acceptance:** If the expected controls are absent, the job enters `NEEDS_USER_ACTION` or `FAILED_UI_CHANGED`, with a screenshot/log reference if safe and useful.

### FR-007 — PDF upload

The browser adapter must upload the exact file selected by the user through the visible interface. It must wait for a visible indication that the attachment is present or otherwise request manual confirmation.

**Acceptance:** The job does not submit the extraction prompt if the attachment state cannot be confirmed.

### FR-008 — Prompt assembly

The extraction prompt must be loaded from a version-controlled prompt file and combined with the canonical schema. The prompt version and schema version must be recorded with the job.

**Acceptance:** The job record identifies which prompt/schema produced each response.

### FR-009 — Prompt submission

The application must submit the prompt through the visible page UI. Submission must be a separate state from upload and generation.

**Acceptance:** A click or keyboard action alone is not considered successful submission; the application must observe a visible conversation change or other stable user-facing signal.

### FR-010 — Completion detection

The application must wait for generation to finish using observable page state and a configurable timeout. It must not assume that a response is complete after a fixed delay.

**Acceptance:** Timeout leads to a recoverable state, not a false `COMPLETED` status.

### FR-011 — Response capture

The application must capture the latest completed assistant response from the rendered conversation using stable, visible-page locators. It must not depend on undocumented private endpoints or internal application state.

**Acceptance:** Captured text is stored before parsing. If the response cannot be uniquely identified, the job must request user review.

### FR-012 — Raw response preservation

The exact captured response must be saved to `data/raw/` before JSON extraction, Markdown-fence removal, repair, or normalization.

**Acceptance:** A parser failure never destroys the only copy of the response.

### FR-013 — JSON parsing

The system must parse the captured response as JSON. If the response includes a single Markdown JSON fence, the parser may remove the surrounding fence in a derived copy. It must not alter the raw response.

**Acceptance:** Invalid JSON is flagged and the raw response remains available. Any repair attempt must be explicit, logged, and produce a separate artifact.

### FR-014 — Schema validation

The parsed result must be checked against the canonical JSON schema and additional semantic validators described in Section 7.

**Acceptance:** A batch cannot be marked `COMPLETED` unless it passes all mandatory structural checks. Content needing human verification must remain flagged.

### FR-015 — Expected question accounting

Where a reliable expected question count is known (for example, from a known source range or user input), compare it to the extracted count. If the count is unknown, record it as unknown rather than inventing one.

**Acceptance:** Count mismatches are surfaced to the user and cannot silently pass.

### FR-016 — Output naming

Outputs must use safe, deterministic names based on the input basename and job/batch identity. Existing files must not be silently overwritten.

**Acceptance:** A repeated job produces a new version or resumes the existing job according to an explicit user choice.

### FR-017 — Checkpointing

The system must persist state after each major transition and after raw/validated artifacts are written. Restarting the app must allow the user to inspect and resume a job from its last safe state.

**Acceptance:** Completed batches are not automatically resubmitted just because the application restarted.

### FR-018 — Error classification

At minimum, distinguish: invalid input, browser launch failure, authentication required, UI changed, upload failure, submission uncertain, generation timeout, usage-limit notice, response capture failure, invalid JSON, schema failure, count mismatch, filesystem failure, and unexpected exception.

**Acceptance:** Every failed job includes a machine-readable error code and a user-readable explanation.

### FR-019 — Bounded retries

Retry only errors classified as transient and only a limited number of times. Before resubmitting, check whether a response may already exist to avoid duplicate work.

**Acceptance:** No infinite retry loop; retry count and wait duration are recorded.

### FR-020 — User control

The user must be able to pause a job, cancel future actions, open the output folder, inspect the raw response, and retry a failed validation step without resubmitting the entire PDF where possible.

**Acceptance:** Pause/cancel is honored at the next safe checkpoint; no claim is made that an already submitted Gemini request can always be cancelled remotely.

### FR-021 — Logging

Record timestamps, state transitions, duration, file hash, prompt/schema versions, retry counts, and sanitized error details. Do not log credentials, cookies, full session data, or unnecessary personal data.

**Acceptance:** Logs help diagnose failures without exposing authentication material.

### FR-022 — UI status

The dashboard must show current job, current state, last successful step, output location, and any required user action. It must not display invented progress percentages when the browser does not expose real progress.

**Acceptance:** Progress is based on confirmed states, completed batches, or known page/question counts.

---

## 5. Non-functional requirements

### NFR-001 — Reliability over apparent speed

The application must prefer a clear recoverable failure over silently corrupting or dropping questions.

### NFR-002 — Local-first storage

Job metadata, raw responses, and generated JSON are stored locally by default. The selected PDF and prompt are sent to Gemini only when the user starts the job.

### NFR-003 — Data integrity

Write output files atomically where practical: write to a temporary file, flush/close it, then rename to the final path. Preserve raw responses as immutable job artifacts.

### NFR-004 — Determinism

For the same job artifact, the application should produce repeatable validation results. Model-generated content itself may differ across runs.

### NFR-005 — Maintainability

Browser selectors must be centralized in the browser adapter, not scattered across UI, queue, and validation code.

### NFR-006 — Observability

Every state transition and failure must be diagnosable through the job record and logs.

### NFR-007 — Bounded resource use

Version 1 runs one browser extraction job at a time and avoids unnecessary PDF copies or full-document screenshots. Large files should be checked against Gemini's current upload/analysis limits before submission where that information is available.

### NFR-008 — Security

Do not commit browser profiles, cookies, credentials, PDFs, raw responses, or private output. Use a `.gitignore` and restrictive local file permissions where available.

### NFR-009 — Usability

Errors must explain the next action, such as sign in manually, inspect the browser, retry after the service permits it, or review invalid JSON.

### NFR-010 — Testability

Core logic (schema validation, naming, checkpoint transitions, parsing, and error classification) must be testable without a live Gemini session. Live browser tests must be separated from offline unit tests.

---

## 6. Architecture

### 6.1 High-level flow

```text
User selects PDF
      |
      v
Input validation + SHA-256
      |
      v
Create/load job record (SQLite)
      |
      v
Launch visible Chromium profile
      |
      v
Manual authentication/readiness check if required
      |
      v
Upload PDF through visible Gemini UI
      |
      v
Confirm attachment + submit prompt/schema
      |
      v
Wait for generation completion (bounded timeout)
      |
      v
Capture rendered assistant response
      |
      v
Save immutable raw response
      |
      v
Parse JSON -> validate schema -> semantic checks
      |                         |
      | valid                   | invalid/uncertain
      v                         v
Write final JSON             Needs review / bounded recovery
      |
      v
Persist completed state + export report
```

### 6.2 Design principles

1. **Separate concerns:** browser interaction, job state, validation, file storage, and UI are separate modules.
2. **One source of truth:** schema and prompt files are version-controlled and loaded at runtime.
3. **Save before transforming:** raw response is written before parsing or repair.
4. **Checkpoint every irreversible stage:** especially after submission, capture, and artifact creation.
5. **No silent fallback:** missing selectors, uncertain completion, malformed output, or usage limits must be surfaced.
6. **Avoid duplicate submissions:** if the application restarts after submission, inspect the existing conversation/job state before submitting again.
7. **Manual recovery is a feature:** the app should pause safely when browser state cannot be interpreted.
8. **No false accuracy claims:** structural validation and factual correctness are different.

### 6.3 Initial technology choices

| Concern | Choice | Reason |
|---|---|---|
| Language | Python 3.11 baseline | Familiar, broad library support |
| Browser automation | Playwright Python API | Browser contexts, locators, upload handling, timeouts |
| Browser | Playwright-managed Chromium | Reproducible automation environment |
| UI | Streamlit after CLI/browser proof of concept | Simple local dashboard; matches prior project experience |
| PDF preflight | PyMuPDF | Check readability, page count, and basic PDF properties; not used as an alternate AI backend in the first browser-only milestone |
| Data validation | Pydantic and/or JSON Schema | Validate the target contract locally |
| Job state | SQLite | Persistent, local, queryable status without a server |
| Artifact storage | Local filesystem | Raw response and final JSON are easy to inspect and back up |
| Tests | pytest | Offline unit tests plus opt-in live browser tests |
| Logging | Python `logging` with rotating file handler | Structured diagnostic records |

Dependencies must be pinned to tested versions in `requirements.txt` after the initial proof of concept passes. Avoid installing unnecessary AI, OCR, GPU, or multi-agent packages in version 1.

---

## 7. Canonical JSON contract and validation

### 7.1 Target schema

The default output is a JSON array of question objects. The current expected fields are:

```json
[
  {
    "type": "MCQ",
    "en": {
      "text": "Question text in English",
      "options": [
        {"id": "opt1", "text": "Option A"},
        {"id": "opt2", "text": "Option B"},
        {"id": "opt3", "text": "Option C"},
        {"id": "opt4", "text": "Option D"}
      ]
    },
    "hi": {
      "text": "प्रश्न हिंदी में",
      "options": [
        {"id": "opt1", "text": "विकल्प A"},
        {"id": "opt2", "text": "विकल्प B"},
        {"id": "opt3", "text": "विकल्प C"},
        {"id": "opt4", "text": "विकल्प D"}
      ]
    },
    "correctOptionId": "opt3",
    "subject": "Subject name",
    "topic": "Specific topic",
    "has_image": false,
    "explanation": {
      "en": "Explanation in English",
      "hi": "व्याख्या हिंदी में"
    }
  }
]
```

This is an illustrative schema shape based on the existing ExamForge AI project context. The actual `schemas/schema_template.json` file must be copied/derived from the existing project's authoritative template and used as the definitive contract. If the real template differs from this example, the template wins; do not use this illustrative example to overwrite a more complete schema.

### 7.2 Mandatory structural checks

- Top-level value is the type required by the canonical schema (currently expected to be an array).
- Every question contains every required field from the schema.
- `type` is an allowed value.
- `en.text` and `hi.text` are non-empty where required.
- Each language's `options` field has the required shape and count for MCQs.
- Option IDs are unique within a question and aligned across languages where the schema expects alignment.
- `correctOptionId` matches one of the option IDs.
- `subject` and `topic` are non-empty strings when required.
- `has_image` is a Boolean.
- `explanation.en` and `explanation.hi` are present and non-empty if required by the canonical schema.
- No unexpected fields are accepted if the schema disallows them; otherwise preserve or report them according to the schema's configured policy.
- Strings are valid Unicode and the file is valid UTF-8.

### 7.3 Content-quality checks

These checks are flags, not proof of correctness:

- Empty or suspiciously short question text.
- Duplicate questions within a batch.
- Missing or duplicate option labels.
- Different option ID sets between English and Hindi.
- `correctOptionId` is missing, unsupported, or appears guessed.
- Source language is absent but a translation is present without a flag.
- Image-dependent question appears to have no image reference or vice versa.
- Explanation contradicts the selected answer or repeats the option without explaining it.
- Question count differs from a known expected count.
- Mathematical notation appears malformed or has lost important symbols.

### 7.4 Correct-answer policy

The system must distinguish:

- **Source-keyed:** answer comes from a source answer key.
- **Solved:** answer was derived from a defensible solution.
- **Uncertain:** answer cannot be established confidently.
- **Missing:** no answer was available.

If the canonical schema has no field for answer provenance or uncertainty, store this information in a separate validation report/job metadata rather than silently changing the public schema. Do not invent a `correctOptionId` when the source and reasoning do not support one. If the schema requires a value, flag the question as needing manual review and do not mark the job fully verified.

### 7.5 Validation statuses

Use separate statuses:

- `schema_valid`: output conforms to the schema.
- `content_review_required`: structure is valid but some content/answer may be uncertain.
- `content_verified`: a human or defined verification process checked content against the source.

The application must not equate `schema_valid` with `content_verified`.

---

## 8. Prompt management

### 8.1 Prompt files

- `prompts/extraction.md`: primary extraction instructions.
- `prompts/repair.md`: narrow repair instructions for malformed/incomplete output, if later approved.
- `schemas/schema_template.json`: canonical output contract.

Version prompt and schema independently. Every job records both versions or their content hashes.

### 8.2 Extraction prompt requirements

The prompt must instruct Gemini to:

1. Read every page in the uploaded PDF.
2. Follow actual visual reading order in multi-column layouts.
3. Preserve original English and Hindi where available.
4. Preserve math, formulas, units, subscripts, superscripts, and scientific notation as accurately as possible.
5. Identify image-dependent questions.
6. Extract answer keys only when present; otherwise solve carefully or flag uncertainty.
7. Provide concise, correct explanations in both languages when required by the schema.
8. Assign a suitable subject and specific topic.
9. Never silently skip questions.
10. Report unreadable or incomplete pages/questions.
11. Return the exact schema and valid JSON only, without Markdown fences or surrounding prose.
12. Perform a final completeness check before returning.

### 8.3 Do not overstuff the prompt

Use a concise, versioned prompt and include the exact schema once per conversation/request as needed. Do not repeatedly append the entire project description or irrelevant instructions. Browser-based Gemini may have its own context and response limits; this must be measured empirically.

### 8.4 Response size and batching

Version 1 should begin with one PDF per job and a configurable extraction unit. Do not assume one entire large PDF will fit in a single request or that a one-page batch is always optimal. First test small representative PDFs. If the UI/API-supported workflow and applicable terms permit page-group batching, choose a conservative batch size and increase it only after completeness testing.

If a single PDF request is too large or output is truncated, pause and ask the user to split the document or use a supported smaller-batch workflow. Do not build a brittle automatic split-and-resubmit loop before the single-PDF proof of concept is reliable.

---

## 9. Browser automation specification

### 9.1 Browser lifecycle

- Use Playwright's persistent browser context with a project-owned profile directory.
- Use `headless=False` for version 1 so the user can see what the automation does.
- Do not use the user's regular Chrome profile.
- Do not store credentials in source code or `.env`.
- Do not export browser cookies or authentication tokens.
- Close the context cleanly when the user closes the job, while preserving the dedicated profile as intended.

### 9.2 Selector strategy

The exact Gemini selectors must be discovered and verified against the live interface at implementation time. They are not specified as constants in this plan because the UI may change.

Preferred selector order:

1. Accessible role and accessible name.
2. Label or placeholder that is visible and stable.
3. Stable visible text associated with the control.
4. A narrowly scoped CSS locator only when accessible locators are unavailable.
5. Screen-coordinate clicking only as a last-resort, supervised fallback—not as the primary approach.

All selectors must live in `browser/gemini_page.py` or a dedicated selector module. Include comments explaining how each selector was verified. Never assume a selector such as `input[type=file]` exists; inspect the actual page and handle the case where the upload mechanism differs.

### 9.3 Completion detection

Completion detection must be based on visible UI signals discovered during implementation, such as the generation control returning to an idle state or another stable page indicator. The exact signal must be verified empirically.

Do not use only a fixed `sleep()` duration as proof that generation is finished. Use explicit waits with timeouts, and allow a manual “response is complete” confirmation if the website state cannot be reliably determined.

### 9.4 Capturing the correct response

- Identify the latest assistant response associated with the current job.
- Do not capture a previous conversation response accidentally.
- If the response appears in multiple parts or multiple blocks, determine whether the UI presents one complete answer or multiple separate messages.
- If response identity/completeness is uncertain, pause for user review.
- Save the raw response before parsing.

### 9.5 Browser recovery

If the browser closes, the page changes unexpectedly, the upload fails, or the app restarts, persist the last confirmed state. On resume, inspect the current visible page and job artifacts before taking any new action. Do not automatically re-submit a prompt when it is uncertain whether the prior submission succeeded.

### 9.6 Browser profile safety

The profile directory contains sensitive session data. It must be excluded from Git, never uploaded as an artifact, and never printed in logs. The application should provide a documented way to sign out or clear the dedicated profile if the user chooses.

---

## 10. Job state machine and recovery

### 10.1 Proposed states

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

Transitions must be explicit and validated in code. A completed state cannot transition backwards without a deliberate reprocess action.

### 10.2 Checkpoint points

Persist state:

- After input validation and hash calculation.
- After creating the job record.
- After the browser launches.
- After manual authentication/readiness confirmation.
- After the upload is confirmed.
- Immediately after submission is confirmed.
- After the response is captured.
- After the raw response file is flushed to disk.
- After parsing and validation.
- After the final JSON and validation report are saved.

### 10.3 Retry policy

- Use a small configurable retry limit, initially no more than two automatic retries for clearly transient operations.
- Add exponential backoff only for errors known to be transient and permitted to retry.
- Do not retry a usage-limit response in a tight loop.
- Do not retry authentication or CAPTCHA challenges automatically.
- Do not re-submit if submission status is uncertain; require inspection or user confirmation.
- Retry parsing/validation from the saved raw response without returning to Gemini.
- Record each attempt and reason.

### 10.4 Idempotency

Use a job ID plus source file hash and prompt/schema version to identify a processing run. Re-running a completed job must require a clear choice: reuse existing result, create a new run, or reprocess. Never overwrite a previous final output silently.

---

## 11. Data storage and output contract

### 11.1 Proposed directory layout

```text
examforge-browser/
├── app.py
├── requirements.txt
├── README.md
├── plan.md
├── .gitignore
├── prompts/
│   ├── extraction.md
│   └── repair.md
├── schemas/
│   └── schema_template.json
├── browser/
│   ├── __init__.py
│   ├── launch.py
│   ├── gemini_page.py
│   └── selectors.py
├── core/
│   ├── __init__.py
│   ├── job_manager.py
│   ├── state_machine.py
│   ├── checkpoint.py
│   ├── config.py
│   └── logging_config.py
├── validation/
│   ├── __init__.py
│   ├── parse_response.py
│   ├── validate_json.py
│   ├── completeness.py
│   └── quality_flags.py
├── storage/
│   ├── __init__.py
│   ├── database.py
│   └── artifacts.py
├── tests/
│   ├── test_parsing.py
│   ├── test_schema.py
│   ├── test_state_machine.py
│   ├── test_naming.py
│   └── test_browser_live.py
└── data/                      # local-only; ignored by Git
    ├── inputs/
    ├── raw/
    ├── outputs/
    ├── reports/
    ├── jobs/
    ├── logs/
    └── browser_profile/
```

The actual browser profile may be placed outside `data/` if that makes backup/exclusion behavior clearer, but it must remain dedicated and ignored by Git.

### 11.2 Job artifacts

For each job, store at least:

- Job metadata (SQLite row and/or a human-readable JSON manifest).
- Source file hash and source filename.
- Raw captured response (`.txt`).
- Parsed/normalized output (`.json`) when parseable.
- Validation report (`.json` or `.md`).
- Sanitized log entries.
- Optional screenshots only for failure diagnosis and only when they do not expose unnecessary sensitive information.

### 11.3 Suggested naming convention

Use safe slugs and a unique job identifier. Example:

```text
data/raw/JTET_2016__job_a1b2c3__raw.txt
data/outputs/JTET_2016__job_a1b2c3.json
data/reports/JTET_2016__job_a1b2c3__validation.json
```

Never use untrusted input filenames directly without sanitization. Never overwrite a different job's output silently.

### 11.4 Validation report example

```json
{
  "job_id": "job_a1b2c3",
  "schema_valid": true,
  "content_review_required": true,
  "expected_question_count": null,
  "extracted_question_count": 42,
  "errors": [],
  "warnings": [
    "Question 17 answer key was not found in the source and requires review."
  ],
  "prompt_version": "1.0.0",
  "schema_version": "1.0.0"
}
```

This report is an example of internal metadata, not an addition to the question JSON schema.

---

## 12. User interface requirements

### 12.1 Initial Streamlit pages/sections

**Dashboard**
- Project status and current job.
- Select PDF.
- Show file name, size, and page count when readable.
- Start, pause, resume, cancel, and open output folder controls.
- Show confirmed progress and last checkpoint.

**Job details**
- Job ID, source hash, prompt/schema version, status, start time, elapsed time.
- State transition history and sanitized error message.
- Links/buttons to open raw response, final JSON, and validation report.

**Review**
- Show schema errors and quality warnings.
- Show question index and relevant validation issue.
- Allow opening the raw response or output JSON in an editor/viewer.
- Do not silently auto-correct factual answer errors.

**Settings**
- Gemini URL (default fixed to official Gemini URL unless a future requirement changes it).
- Timeouts and retry limits.
- Output directory.
- Prompt/schema version display.
- Button to open or reset the dedicated browser profile with a warning.

### 12.2 UI behavior

- Disable Start when there is no valid input or another browser job is active.
- Do not claim “100% complete” until the output has been captured, saved, and validated.
- Display actionable errors, not raw stack traces as the only message.
- Offer a details panel for technical logs.
- Ask for confirmation before deleting data, clearing the browser profile, or reprocessing a completed job.

---

## 13. Error handling matrix

| Error category | Required behavior | Automatic retry? |
|---|---|---|
| Invalid/missing PDF | Stop before browser interaction; explain fix | No |
| PDF unreadable/password-protected | Explain limitation; ask for an accessible file | No |
| Browser not installed/launch failure | Show installation or environment guidance | Limited after environment fix |
| Login required | Pause for manual sign-in | No automatic login |
| CAPTCHA/security challenge | Pause and ask user to handle manually | No bypass/retry loop |
| Gemini page not ready | Wait for bounded timeout, then pause | One cautious retry if clearly transient |
| Selector missing/UI changed | Save diagnostic information and stop | No blind retry |
| Upload failed | Verify current attachment state before retry | Limited if clearly failed |
| Submission uncertain | Inspect page and ask user if necessary | No blind resubmission |
| Generation timeout | Preserve job and visible state; allow manual check | Limited and only after checking whether response exists |
| Usage limit/quota notice | Pause; show message; resume only when permitted | No immediate repeated retry |
| Response capture ambiguous | Preserve state; request user review | No |
| Invalid JSON | Save raw response; attempt parsing/repair only as a separate step | Retry parser offline first |
| Schema invalid | Generate a validation report; optionally request narrow repair later | No full-document rerun by default |
| Question count mismatch | Mark incomplete/review required | No silent success |
| Disk full/write failure | Stop before marking completed; preserve any already saved raw data | Retry after user fixes storage |
| Unexpected exception | Record sanitized traceback, persist state, stop safely | Depends on classified cause |

---

## 14. Testing strategy

### 14.1 Offline unit tests (must run without Gemini)

- Valid JSON is parsed.
- Markdown-fenced JSON can be parsed from a derived copy.
- Invalid JSON fails cleanly without changing raw text.
- Missing required fields are rejected.
- Missing Hindi explanation is flagged.
- Wrong option count is rejected.
- Unknown `correctOptionId` is rejected.
- Duplicate option IDs are rejected.
- Boolean `has_image` is enforced.
- Question-count mismatch is reported.
- Unsafe filenames are sanitized.
- Existing output is not silently overwritten.
- State transitions reject invalid jumps.
- Restart/resume loads the last persisted state.
- Logs omit session data and secrets.

### 14.2 Browser integration tests

Use a dedicated test profile and a small, non-sensitive test PDF. Live tests may require manual authentication and are not suitable for every CI run.

Test:

- Browser launch and Gemini navigation.
- Manual authentication pause/resume.
- Upload detection.
- Prompt submission confirmation.
- Generation completion detection.
- Response capture.
- Raw response persistence.
- Browser close/reopen recovery.
- UI-change detection when a selector is intentionally invalidated in a test double or mocked page.

### 14.3 End-to-end test corpus

Use at least three representative PDFs:

1. Clean digital PDF with selectable text and two-column layout.
2. Scanned or image-heavy bilingual paper.
3. Paper containing mathematics, scientific notation, diagrams, or long options.

Where available, compare output to a manually verified reference set. Record both exact schema success and content correctness. Do not use only one easy PDF to declare the project reliable.

### 14.4 Quality metrics

Record:

- Pages in source.
- Expected question count, if known.
- Extracted question count.
- Questions with complete bilingual fields.
- Schema-valid question percentage.
- Human-reviewed correct-answer percentage on the test set.
- Number of duplicate or missing questions.
- Total elapsed time.
- Manual interventions.
- Browser failures, response truncations, and retries.

Set performance targets only after the first baseline run. Do not invent an expected speedup in advance.

---

## 15. Security, privacy, and policy requirements

- Use a dedicated local browser profile.
- Never ask the user to paste a password into the app.
- Never commit the browser profile or session cookies.
- Never log authentication tokens, cookies, or private profile contents.
- Keep PDFs and generated question banks local unless the user knowingly uploads them to Gemini.
- Clearly communicate that uploading a PDF sends its contents to the Gemini service and is subject to the applicable service terms and privacy settings.
- Do not bypass account limits, CAPTCHA, anti-abuse systems, or access controls.
- Do not use undocumented private API endpoints.
- Respect the website's applicable terms and current usage restrictions. If the intended automation is not permitted, stop and use a supported workflow instead.
- Treat generated explanations and answer keys as untrusted until validated/reviewed.
- Keep logs minimal and configurable; provide a way to remove local job artifacts and the dedicated browser profile.

---

## 16. Installation and developer workflow

### 16.1 Create environment (PowerShell)

```powershell
mkdir examforge-browser
cd examforge-browser
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If Python 3.11 is not installed, check available versions using `py --list` and choose a Python version supported by all pinned dependencies. Do not assume the `py -3.11` command will work on every machine.

### 16.2 Initial dependencies

The first browser proof of concept needs only a small dependency set, for example:

```text
playwright
pymupdf
pydantic
jsonschema
pytest
streamlit
```

Install Playwright and its browser runtime:

```powershell
pip install -r requirements.txt
playwright install chromium
```

After successful testing, pin exact dependency versions in `requirements.txt`. Do not use unbounded dependency upgrades in a production run without testing.

### 16.3 Development sequence

1. Create repository, `.gitignore`, `README.md`, and `plan.md`.
2. Build and test browser launch only.
3. Inspect Gemini UI manually and document verified selectors.
4. Implement upload detection.
5. Implement prompt submission and completion detection.
6. Implement response capture and raw artifact saving.
7. Implement parser and schema validator with offline fixtures.
8. Add SQLite job state/checkpoints.
9. Add Streamlit UI.
10. Run the end-to-end corpus and record results.
11. Fix failure cases before adding batch/multi-file processing.

### 16.4 Git safety

Suggested `.gitignore` entries:

```gitignore
.venv/
__pycache__/
.pytest_cache/
.env
browser_profile/
data/
*.log
playwright-report/
```

Keep `plan.md`, source code, prompt templates, schema templates, tests, and a sanitized example configuration under version control. Do not commit real examination PDFs unless their distribution is permitted and intentionally desired.

---

## 17. Proposed module responsibilities

### `app.py`

Streamlit entry point. It should call job-manager methods and render state; it must not contain selector logic, parsing logic, or raw database queries scattered through callbacks.

### `browser/launch.py`

Launch/close the dedicated persistent browser context. Handle visible browser lifecycle and clear launch errors.

### `browser/gemini_page.py`

Own Gemini-specific page interactions: readiness, upload, submission, completion detection, and visible response capture. Keep selectors localized here.

### `browser/selectors.py`

Centralize selectors discovered from the live UI, with comments about the element role/name and verification date. Do not put speculative selectors here as if they were verified.

### `core/job_manager.py`

Create jobs, enforce one-active-job policy, invoke state transitions, coordinate browser and validation operations, and implement pause/resume/cancel behavior.

### `core/state_machine.py`

Define allowed statuses and transitions. Reject illegal transitions and record transition timestamps.

### `core/checkpoint.py`

Persist checkpoints and recover jobs after restart. Ensure raw response/output files are written before the job is marked as saved/completed.

### `core/config.py`

Load defaults and validated user settings. Keep secrets out of config; the project should not need Gemini API keys for browser-only operation.

### `core/logging_config.py`

Configure structured logs and redact sensitive values.

### `validation/parse_response.py`

Extract JSON from a captured response into a derived representation without modifying the raw artifact.

### `validation/validate_json.py`

Apply the canonical JSON Schema/Pydantic checks and return structured errors/warnings.

### `validation/completeness.py`

Check expected question counts and detect suspicious gaps/duplicates when reliable reference data exists.

### `validation/quality_flags.py`

Flag potential content-quality issues without claiming to prove factual correctness.

### `storage/database.py`

Manage SQLite connection, schema migrations, job records, and transaction boundaries.

### `storage/artifacts.py`

Write/read raw responses, final JSON, validation reports, and optional diagnostic files using safe paths and atomic writes.

---

## 18. Definition of done for version 1

Version 1 is not done merely because it can open Gemini and submit a prompt. It is done only when all of the following are true:

- [ ] Project is isolated from the existing ExamForge repository.
- [ ] Installation instructions work on the target Windows environment.
- [ ] Browser launches visibly with a dedicated profile.
- [ ] Manual authentication is supported without storing credentials.
- [ ] Upload success is confirmed before prompt submission.
- [ ] Prompt and schema versions are recorded.
- [ ] Generation completion is detected or the job pauses for manual confirmation.
- [ ] Latest response is captured from the visible conversation.
- [ ] Raw response is saved before parsing.
- [ ] JSON and schema validation are implemented and unit-tested.
- [ ] Invalid/incomplete output is never marked completed.
- [ ] Checkpoint/resume works after an application restart.
- [ ] Retry behavior is bounded and usage limits cause a safe pause.
- [ ] Outputs never overwrite other job results silently.
- [ ] Logs and Git configuration protect the browser profile and private files.
- [ ] At least three representative PDFs have been tested and results recorded.
- [ ] The README documents known limitations and manual recovery procedures.

---

## 19. Known risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Gemini UI changes | Upload/submission/capture breaks | Centralize selectors, detect missing elements, pause rather than guessing |
| Website policy or terms do not permit intended automation | Project cannot be used as designed | Verify applicable terms before implementation; stop or use supported alternatives if not permitted |
| Usage limit reached | Job cannot continue immediately | Preserve checkpoint and pause; never loop retries to evade limits |
| Long response is truncated | Missing questions or invalid JSON | Save raw response, detect count/schema issues, use smaller supported batches where feasible |
| Gemini skips questions | Incomplete question bank | Compare counts where known, require completeness checks, review output |
| Wrong answer key/explanation | Educational content error | Track uncertainty, preserve source, human-review critical content |
| Browser submits twice | Duplicate work or confusing conversation | Explicit state machine and submission-uncertainty handling |
| Browser profile is exposed | Account/session compromise | Dedicated profile, Git exclusion, no cookie export, clear/reset option |
| App crashes after response | Lost work or duplicate submission | Save response immediately and checkpoint every major stage |
| Output overwrites earlier file | Data loss | Unique job IDs, atomic writes, collision-safe naming |
| Large PDF exceeds website limits | Upload/analysis failure | Preflight, test file size/page limits, supported smaller batches if permitted |
| Automation depends on fixed sleeps | Flaky timing | Use observable page state, explicit waits, bounded timeouts |
| False progress display | User believes job is complete when it is not | Only report confirmed state and completed artifacts |

---

## 20. Open decisions to resolve during implementation

These are intentionally not guessed in advance because they depend on the live website, authoritative schema, and test PDFs:

1. **Exact Gemini upload locator:** inspect and verify against the current UI.
2. **Exact composer locator:** inspect and verify against the current UI.
3. **Exact generation-complete signal:** determine which visible signal is stable and test it.
4. **Exact response locator:** determine how to isolate the latest assistant response.
5. **Canonical schema file:** copy the authoritative template from the existing ExamForge project; this plan's example is not a substitute.
6. **Maximum supported input size/page count:** verify current Gemini UI limits and test realistic PDFs before choosing limits.
7. **Batch strategy:** begin conservatively and use measured completeness, response length, and elapsed time to decide whether to process one PDF or smaller page groups.
8. **Question-count expectation:** determine whether it can be provided by the user or derived reliably from a source/answer key.
9. **Screenshot retention:** decide whether diagnostic screenshots should be retained and for how long; avoid retaining sensitive page content unnecessarily.
10. **Final UI details:** build only after the browser proof of concept confirms the core interaction path.

The project must document each decision when resolved. Do not fill these items with fabricated selectors, guessed limits, or unverified claims.

---

## 21. First implementation milestone: browser proof of concept

The first milestone should contain only:

1. A Python virtual environment and minimal dependencies.
2. A script that launches visible Chromium with a dedicated persistent profile.
3. Navigation to Gemini.
4. Manual sign-in/readiness pause.
5. A documented, verified way to upload one small test PDF.
6. A documented, verified way to submit one prompt.
7. A reliable or manually confirmed way to determine generation completion.
8. Capture of the latest response from the visible page.
9. Saving that response to a raw `.txt` file.
10. A short test report describing what worked, what failed, and which UI selectors were verified.

**Milestone exit criteria:** the same small test can be run twice without mixing responses, losing the raw response, or silently reporting a failure as success. If any of those conditions fail, fix the proof of concept before proceeding to JSON validation and the dashboard.

---

## 22. Final engineering rule

When uncertain, the application must stop, preserve its state, and explain what needs attention. It must never silently discard questions, invent answer certainty, overwrite prior results, or report success just because Gemini produced a response.

The governing priority is:

**Data integrity and traceability first; extraction completeness second; speed and convenience third.**
