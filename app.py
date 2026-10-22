"""
ExamForge Browser — Streamlit Control Dashboard.
Interactive user interface for managing browser extraction jobs, inspecting bilingual outputs,
viewing audit trails, and managing persistent configurations.
"""
from pathlib import Path
import json
import streamlit as st
import time
import shutil

from core.config import config
from core.state_machine import JobState
from core.job_manager import job_manager, inspect_pdf, calculate_sha256
from storage.database import db
from storage.artifacts import artifacts

st.set_page_config(
    page_title="ExamForge Browser",
    page_icon="📑",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📑 ExamForge Browser")
st.caption("Bilingual Question-Bank Browser Automation & Verification Platform")

# Top metrics / Active Job Banner
active_job = job_manager.get_active_job()
if active_job:
    status_val = active_job["status"]
    if status_val == JobState.WAITING_FOR_AUTH.value:
        st.warning(
            f"🔑 **Sign-In Required:** Job `{active_job['id']}` is waiting for you to sign in to your Google Account in the visible Chromium window."
        )
    elif status_val == JobState.NEEDS_USER_ACTION.value:
        st.warning(
            f"⚠️ **Action Required:** Job `{active_job['id']}` needs your review. Status: **{status_val}**"
        )
    else:
        st.info(
            f"🔄 **Job In Progress:** `{active_job['id']}` | Status: **{status_val}** | Source: `{active_job['source_filename']}`"
        )

# Sidebar
st.sidebar.header("Job Control")
tab_selection = st.sidebar.radio(
    "Navigation",
    ["🚀 Dashboard", "📋 Job Ledger", "🔍 Question Review", "⚙️ Settings"],
)

# ----------------------------------------------------
# TAB 1: DASHBOARD
# ----------------------------------------------------
if tab_selection == "🚀 Dashboard":
    st.subheader("Document Extraction Workflow")

    col1, col2 = st.columns([1.2, 1])

    with col1:
        st.markdown("### 1. Document Selection")
        uploaded_file = st.file_uploader("Upload examination PDF", type=["pdf"])
        manual_path = st.text_input(
            "Or enter absolute path to local PDF",
            placeholder="e.g. D:\\Classroom\\Coding\\sample_exam.pdf",
        )

        target_pdf_path = None
        if uploaded_file is not None:
            config.ensure_directories()
            saved_path = config.inputs_dir / uploaded_file.name
            file_bytes = uploaded_file.getvalue()
            # Only write if file does not exist or size changed to prevent ERR_UPLOAD_FILE_CHANGED during upload
            if not saved_path.exists() or saved_path.stat().st_size != len(file_bytes):
                with open(saved_path, "wb") as f:
                    f.write(file_bytes)
            target_pdf_path = saved_path
        elif manual_path.strip():
            candidate = Path(manual_path.strip())
            if candidate.exists() and candidate.is_file():
                target_pdf_path = candidate

        expected_count_input = st.number_input(
            "Expected Question Count (optional, 0 if unknown)", min_value=0, value=0, step=1
        )
        expected_count = int(expected_count_input) if expected_count_input > 0 else None

        if target_pdf_path:
            try:
                size_bytes, page_count = inspect_pdf(target_pdf_path)
                sha = calculate_sha256(target_pdf_path)
                st.success(f"**Valid PDF Selected:** `{target_pdf_path.name}`")
                mcol1, mcol2, mcol3 = st.columns(3)
                mcol1.metric("Pages", page_count)
                mcol2.metric("Size", f"{size_bytes / 1024:.1f} KB")
                mcol3.metric("SHA-256 (prefix)", sha[:10])
            except Exception as e:
                st.error(f"Invalid PDF: {e}")
                target_pdf_path = None

    with col2:
        st.markdown("### 2. Execution Controls")
        active = job_manager.get_active_job()

        start_disabled = (target_pdf_path is None) or (active is not None)

        if st.button("🚀 Start Extraction Job", disabled=start_disabled, type="primary"):
            try:
                new_job = job_manager.create_job(target_pdf_path, expected_count=expected_count)
                job_manager.start_job_async(new_job["id"], target_pdf_path, expected_count=expected_count)
                st.success(f"Job `{new_job['id']}` started! Chromium browser launched.")
                time.sleep(1)
                st.rerun()
            except Exception as ex:
                st.error(f"Job initialization error: {ex}")

        if active:
            st.divider()
            st.markdown(f"**Current Job:** `{active['id']}`")
            st.markdown(f"**Current State:** `{active['status']}`")

            if active["status"] == JobState.WAITING_FOR_AUTH.value:
                st.info(
                    "👉 **Please sign in to Google in the visible Chromium window.**\n\n"
                    "Once you are signed in and Gemini loads, the automation will automatically detect it and continue."
                )
            elif active["status"] == JobState.NEEDS_USER_ACTION.value:
                st.warning(
                    "👉 **Auto-Approval Available:** The job requires confirmation (e.g. upload chip verification).\n\n"
                    "Click **'Auto-Approve & Continue'** to immediately approve and send the prompt to Gemini."
                )
                if st.button("✅ Auto-Approve & Continue", type="primary"):
                    try:
                        job_manager.auto_approve_and_resume(active["id"])
                        st.success(f"Job `{active['id']}` auto-approved! Resuming pipeline...")
                        time.sleep(1)
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Error resuming job: {ex}")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("⏸ Pause Job", type="secondary"):
                    job_manager.pause_job(active["id"])
                    st.warning("Job paused.")
                    st.rerun()
            with c2:
                if st.button("🛑 Cancel Job", type="secondary"):
                    job_manager.cancel_job(active["id"])
                    st.error("Job cancelled.")
                    st.rerun()

            # Auto-refresh loop while job is actively running in background
            if active["status"] != JobState.NEEDS_USER_ACTION.value:
                time.sleep(2)
                st.rerun()

        st.divider()
        st.markdown("### 3. Artifact Folders")
        fcol1, fcol2 = st.columns(2)
        with fcol1:
            st.caption(f"Raw responses: `{config.raw_dir}`")
            st.caption(f"Final JSON: `{config.outputs_dir}`")
        with fcol2:
            st.caption(f"Validation reports: `{config.reports_dir}`")
            st.caption(f"Logs: `{config.logs_dir}`")

# ----------------------------------------------------
# TAB 2: JOB LEDGER
# ----------------------------------------------------
elif tab_selection == "📋 Job Ledger":
    st.subheader("Historical & Active Jobs")
    jobs = db.list_jobs(limit=100)

    if not jobs:
        st.info("No jobs recorded in database yet.")
    else:
        selected_job_id = st.selectbox(
            "Select Job to Inspect",
            [f"{j['id']} | {j['source_filename']} | [{j['status']}]" for j in jobs],
        )
        job_id = selected_job_id.split(" | ")[0]
        job = db.get_job(job_id)

        if job:
            st.markdown(f"#### Job Details: `{job['id']}`")
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("Status", job["status"])
            col_b.metric("Pages", job["source_page_count"])
            col_c.metric("Prompt Ver", job["prompt_version"])
            col_d.metric("Created At", job["created_at"][:19])

            if job.get("error_message"):
                st.error(f"Error [{job.get('error_code')}]: {job.get('error_message')}")

            # Action & Download buttons
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                # Offline reprocess button if raw response exists
                if job.get("raw_path") and Path(job["raw_path"]).exists():
                    if st.button("🔄 Reprocess Raw Response Offline"):
                        with open(job["raw_path"], "r", encoding="utf-8") as rf:
                            raw_content = rf.read()
                        with st.spinner("Reparsing and revalidating..."):
                            job_manager.process_raw_response_offline(
                                job["id"], job["source_filename"], raw_content
                            )
                        st.success("Reprocess completed!")
                        st.rerun()

            with btn_col2:
                if job.get("output_path") and Path(job["output_path"]).exists():
                    out_p = Path(job["output_path"])
                    with open(out_p, "r", encoding="utf-8") as f:
                        j_bytes = f.read()
                    st.download_button(
                        label="📥 Download Final JSON",
                        data=j_bytes,
                        file_name=out_p.name,
                        mime="application/json",
                        type="primary",
                        key=f"dl_ledger_{job['id']}",
                    )

            st.markdown("##### State Transition Audit Trail")
            transitions = db.get_job_transitions(job_id)
            for t in transitions:
                note_str = f" — *{t['note']}*" if t["note"] else ""
                st.markdown(
                    f"- `{t['timestamp'][:19]}`: **{t['from_state'] or 'START'}** ➔ **{t['to_state']}**{note_str}"
                )

# ----------------------------------------------------
# TAB 3: QUESTION REVIEW
# ----------------------------------------------------
elif tab_selection == "🔍 Question Review":
    st.subheader("Question Bank Quality & Content Review")
    jobs = db.list_jobs(limit=100)
    completed_jobs = [j for j in jobs if j.get("output_path")]

    if not completed_jobs:
        st.info("No parsed question outputs found yet.")
    else:
        job_options = {f"{j['id']} — {j['source_filename']}": j for j in completed_jobs}
        choice = st.selectbox("Choose Job to Review", list(job_options.keys()))
        selected_job = job_options[choice]

        output_path = Path(selected_job["output_path"])
        report_path = (
            Path(selected_job["report_path"]) if selected_job.get("report_path") else None
        )
        raw_path = (
            Path(selected_job["raw_path"]) if selected_job.get("raw_path") else None
        )

        # Direct Artifact Download Actions
        dl_col1, dl_col2, dl_col3 = st.columns(3)
        with dl_col1:
            if output_path.exists():
                with open(output_path, "r", encoding="utf-8") as f:
                    final_json_text = f.read()
                st.download_button(
                    label="📥 Download Final JSON",
                    data=final_json_text,
                    file_name=output_path.name,
                    mime="application/json",
                    type="primary",
                    key=f"dl_rev_json_{selected_job['id']}",
                )
        with dl_col2:
            if report_path and report_path.exists():
                with open(report_path, "r", encoding="utf-8") as f:
                    report_json_text = f.read()
                st.download_button(
                    label="📊 Download Validation Report",
                    data=report_json_text,
                    file_name=report_path.name,
                    mime="application/json",
                    key=f"dl_rev_rep_{selected_job['id']}",
                )
        with dl_col3:
            if raw_path and raw_path.exists():
                with open(raw_path, "r", encoding="utf-8") as f:
                    raw_resp_text = f.read()
                st.download_button(
                    label="📝 Download Raw Response",
                    data=raw_resp_text,
                    file_name=raw_path.name,
                    mime="text/plain",
                    key=f"dl_rev_raw_{selected_job['id']}",
                )

        st.divider()

        r_col1, r_col2 = st.columns([1, 1])

        # Validation Summary
        if report_path and report_path.exists():
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)

            with r_col1:
                st.markdown("#### Validation Report")
                st.write(f"**Schema Conformance:** {'✅ PASS' if report['schema_valid'] else '❌ FAIL'}")
                st.write(
                    f"**Content Review Required:** {'⚠️ YES' if report['content_review_required'] else '✅ NO'}"
                )
                st.write(f"**Extracted Questions:** {report['extracted_question_count']}")
                if report.get("errors"):
                    st.error("Validation Errors:")
                    for err in report["errors"]:
                        st.write(f"- {err}")
                if report.get("warnings"):
                    st.warning("Quality Warnings:")
                    for w in report["warnings"]:
                        st.write(f"- {w}")

        with r_col2:
            st.markdown("#### Raw Response vs Final JSON")
            v_choice = st.radio("Display Artifact", ["Parsed JSON", "Raw Captured Text"])
            if v_choice == "Parsed JSON" and output_path.exists():
                with open(output_path, "r", encoding="utf-8") as f:
                    st.json(json.load(f))
            elif selected_job.get("raw_path") and Path(selected_job["raw_path"]).exists():
                with open(selected_job["raw_path"], "r", encoding="utf-8") as f:
                    st.text_area("Raw Response Text", f.read(), height=350)

        st.divider()
        st.markdown("### Bilingual Question Cards")
        if output_path.exists():
            with open(output_path, "r", encoding="utf-8") as f:
                questions = json.load(f)

            if isinstance(questions, list):
                for idx, q in enumerate(questions):
                    with st.expander(f"Question #{idx + 1}: {q.get('subject', '')} / {q.get('topic', '')} ({q.get('type')})", expanded=(idx == 0)):
                        q_col1, q_col2 = st.columns(2)
                        with q_col1:
                            st.markdown("**English**")
                            st.write(q.get("en", {}).get("text", ""))
                            for opt in q.get("en", {}).get("options", []):
                                opt_id = opt.get("id")
                                is_correct = opt_id == q.get("correctOptionId")
                                prefix = "🟢 **[CORRECT]** " if is_correct else "⚪ "
                                st.write(f"{prefix} **{opt_id}**: {opt.get('text')}")
                            st.caption(f"Explanation (EN): {q.get('explanation', {}).get('en', '')}")

                        with q_col2:
                            st.markdown("**Hindi**")
                            st.write(q.get("hi", {}).get("text", ""))
                            for opt in q.get("hi", {}).get("options", []):
                                opt_id = opt.get("id")
                                is_correct = opt_id == q.get("correctOptionId")
                                prefix = "🟢 **[CORRECT]** " if is_correct else "⚪ "
                                st.write(f"{prefix} **{opt_id}**: {opt.get('text')}")
                            st.caption(f"Explanation (HI): {q.get('explanation', {}).get('hi', '')}")

                        st.write(f"Image dependent: `{q.get('has_image')}`")

# ----------------------------------------------------
# TAB 4: SETTINGS
# ----------------------------------------------------
elif tab_selection == "⚙️ Settings":
    st.subheader("System Settings & Browser Profile")

    st.markdown("#### Browser Automation Parameters")
    st.text_input("Gemini Target URL", value=config.gemini_url, disabled=True)
    st.write(f"Browser Profile Directory: `{config.browser_profile_dir}`")

    s_col1, s_col2 = st.columns(2)
    with s_col1:
        st.number_input("Page Load Timeout (s)", value=config.page_load_timeout_s, disabled=True)
        st.number_input("Generation Timeout (s)", value=config.generation_timeout_s, disabled=True)
    with s_col2:
        st.number_input("Max Retries", value=config.max_retries, disabled=True)
        st.text_input("Prompt Version", value=config.prompt_version, disabled=True)

    st.divider()
    st.markdown("#### Automation Policies")
    auto_approve_toggle = st.checkbox(
        "Auto-approve user permission when attachment chip is pending",
        value=config.auto_approve_permission,
        help="When enabled, pipeline will automatically proceed with prompt submission if attachment chip is not immediately verified."
    )
    config.auto_approve_permission = auto_approve_toggle

    st.divider()
    st.markdown("#### Dedicated Profile Management")
    st.warning("Resetting the browser profile will remove saved Google session cookies and require re-authentication.")
    if st.button("⚠️ Reset / Clear Dedicated Browser Profile", type="secondary"):
        browser_manager.close()
        if config.browser_profile_dir.exists():
            try:
                shutil.rmtree(config.browser_profile_dir)
                config.browser_profile_dir.mkdir(parents=True, exist_ok=True)
                st.success("Browser profile cleared successfully.")
            except Exception as e:
                st.error(f"Failed to clear profile: {e}")
