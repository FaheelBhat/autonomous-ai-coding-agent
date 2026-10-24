"""Streamlit Web Dashboard for the Autonomous AI Coding Agent."""

import json
import os
import time
import requests
import streamlit as st

# Configure page metadata
st.set_page_config(
    page_title="Autonomous AI Coding Agent",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling for modern aesthetic
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #6366f1, #06b6d4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #94a3b8;
        margin-bottom: 1.5rem;
    }
    .badge-success {
        background-color: #065f46;
        color: #34d399;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-failure {
        background-color: #7f1d1d;
        color: #f87171;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .metric-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Sidebar Settings
st.sidebar.title("⚙️ Agent Controls")
api_url = st.sidebar.text_input(
    "FastAPI Service URL",
    value=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"),
    help="Target backend API endpoint",
)

st.sidebar.markdown("---")
st.sidebar.subheader("Security & Runtime Info")
try:
    health_resp = requests.get(f"{api_url}/health", timeout=2.0)
    if health_resp.status_code == 200:
        health_data = health_resp.json()
        docker_ready = health_data.get("docker_sandbox_available", False)
        if docker_ready:
            st.sidebar.success("🔒 Docker Sandbox: ACTIVE & ISOLATED")
        else:
            st.sidebar.error("⚠️ Docker Sandbox: UNAVAILABLE")
        st.sidebar.info(f"🤖 LLM Provider: {health_data.get('llm_provider', 'Unknown')}")
    else:
        st.sidebar.warning(f"Backend returned status {health_resp.status_code}")
except Exception:
    st.sidebar.error("❌ Cannot connect to FastAPI backend. Ensure `uvicorn api.server:app` is running.")

st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    **Isolation Features:**
    - Non-root UID execution
    - Disabled container networking
    - CPU quota & 256MB RAM cap
    - Read-only workspace mounts
    - 15s execution timeout
    """
)

# Main Title
st.markdown('<div class="main-header">Autonomous AI Coding Agent</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Automated Problem Synthesis, Isolated Sandbox Execution, & Test-Driven Self-Repair</div>',
    unsafe_allow_html=True,
)

# Top Tabs
tab_create, tab_history = st.tabs(["🚀 New Coding Task", "📊 Task History & Inspection"])

with tab_create:
    col_input, col_options = st.columns([3, 1])

    with col_input:
        task_prompt = st.text_area(
            "Programming Problem Description",
            height=140,
            placeholder="e.g. Write a function `longest_palindrome(s: str) -> str` that finds the longest palindromic substring in s. Optimize for O(n^2) or better.",
            help="Describe the algorithmic or programming task in natural language.",
        )
        task_reqs = st.text_area(
            "Specific Constraints & Edge Cases (Optional)",
            height=80,
            placeholder="e.g. Must handle empty string, single characters, and string length up to 1000 without MemoryError.",
        )

    with col_options:
        language = st.selectbox("Language", ["python"], index=0, disabled=True)
        max_repairs = st.slider(
            "Max Repair Attempts",
            min_value=0,
            max_value=6,
            value=3,
            help="Number of iterative self-repair attempts if automated unit tests fail.",
        )
        run_btn = st.button("⚡ Run Autonomous Agent", use_container_width=True, type="primary")

    if run_btn:
        if not task_prompt.strip():
            st.error("Please provide a programming problem prompt.")
        else:
            with st.spinner("Submitting task to agent backend..."):
                payload = {
                    "prompt": task_prompt,
                    "requirements": task_reqs if task_reqs.strip() else None,
                    "language": language,
                    "max_repair_attempts": max_repairs,
                }
                try:
                    submit_resp = requests.post(f"{api_url}/tasks", json=payload, timeout=5.0)
                    if submit_resp.status_code == 202:
                        task_data = submit_resp.json()
                        task_id = task_data["task_id"]
                        st.session_state["current_task_id"] = task_id
                        st.success(f"Task dispatched with ID: `{task_id}`")
                    else:
                        st.error(f"Submission failed: {submit_resp.text}")
                except Exception as e:
                    st.error(f"Connection failed: {str(e)}")

    # Polling & Visualizing Active/Completed Task
    active_task_id = st.session_state.get("current_task_id")
    if active_task_id:
        st.markdown("---")
        st.subheader(f"Task Monitor: `{active_task_id}`")

        progress_placeholder = st.empty()
        status_container = st.empty()

        # Polling loop
        done = False
        task_info = None

        with progress_placeholder.container():
            with st.spinner("Agent working: synthesizing code, building test suite, and executing sandbox..."):
                for _ in range(60):
                    try:
                        res = requests.get(f"{api_url}/tasks/{active_task_id}", timeout=3.0)
                        if res.status_code == 200:
                            task_info = res.json()
                            status_val = task_info.get("status")
                            if status_val in ["completed", "failed"]:
                                done = True
                                break
                    except Exception:
                        pass
                    time.sleep(1.5)

        progress_placeholder.empty()

        if task_info:
            report = task_info.get("report")
            if report:
                # Top summary metrics
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Final Status", report["final_status"].upper())
                m2.metric("Tests Passed", f"{report['test_summary'].get('passed_tests', 0)} / {report['test_summary'].get('total_tests', 0)}")
                m3.metric("Repair Iterations", f"{report['repair_attempts_used']} / {report['max_repair_attempts']}")
                m4.metric("Sandbox Latency", f"{report['test_summary'].get('duration_ms', 0)} ms")

                # Status Banner
                if report["all_tests_passed"]:
                    st.markdown(
                        '<div style="background-color:#064e3b; padding:12px; border-radius:8px; color:#6ee7b7; margin-bottom:15px;">'
                        '✅ <strong>SUCCESS:</strong> All unit tests passed within the secure sandbox! Code is verified.'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        '<div style="background-color:#450a0a; padding:12px; border-radius:8px; color:#fca5a5; margin-bottom:15px;">'
                        '❌ <strong>INCOMPLETE:</strong> Solution did not satisfy all test assertions or sandbox failed.'
                        '</div>',
                        unsafe_allow_html=True,
                    )

                # Explanation
                st.markdown(f"**Approach / Explanation:** {report.get('brief_explanation', 'N/A')}")

                # Code & Tests view
                col_code, col_tests = st.columns(2)
                with col_code:
                    st.subheader("Generated Solution (`solution.py`)")
                    st.code(report["final_code"], language="python")
                    st.download_button(
                        label="⬇️ Download solution.py",
                        data=report["final_code"],
                        file_name="solution.py",
                        mime="text/x-python",
                    )

                with col_tests:
                    st.subheader("Automated Test Suite (`test_solution.py`)")
                    st.code(report["generated_tests"], language="python")

                # Repair History Accordion
                repair_history = report.get("repair_history", [])
                if repair_history:
                    st.markdown("### 🔄 Iterative Self-Repair History")
                    for step in repair_history:
                        num = step["iteration_number"]
                        passed = step["test_evaluation"]["all_passed"]
                        badge = "✅ Passed" if passed else f"❌ Failed ({step['test_evaluation']['primary_failure_category']})"
                        title = f"Iteration {num} — {badge}"
                        with st.expander(title, expanded=(num == len(repair_history) - 1)):
                            st.write(f"**Feedback / Traceback:**")
                            st.code(step["feedback_provided"] or "Initial pass", language="text")
                            st.write(f"**Attempted Code:**")
                            st.code(step["attempted_code"], language="python")

                # Download Structured JSON Report
                report_json_str = json.dumps(report, indent=2)
                st.download_button(
                    label="⬇️ Download Full Execution Report (JSON)",
                    data=report_json_str,
                    file_name=f"report_{active_task_id}.json",
                    mime="application/json",
                )
            else:
                st.warning(f"Task is in status: {task_info.get('status')}. No final report generated yet.")

with tab_history:
    st.subheader("Historical Tasks & Runs")
    if st.button("🔄 Refresh History"):
        st.rerun()

    try:
        from database.db import DatabaseManager
        db_inst = DatabaseManager()
        recent = db_inst.list_tasks(limit=25)
        if recent:
            st.dataframe(
                recent,
                use_container_width=True,
                column_config={
                    "task_id": "Task ID",
                    "status": "Status",
                    "prompt": "Prompt",
                    "created_at": "Submitted At",
                },
            )
        else:
            st.info("No recorded tasks found in SQLite database yet.")
    except Exception as e:
        st.error(f"Could not load database records: {e}")
