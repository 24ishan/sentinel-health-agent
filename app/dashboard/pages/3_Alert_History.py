"""
Alert History Page — Per-patient alert timeline.
Shows a full history of clinical alerts for a selected patient with:
  • Heart rate line chart over time
  • Alert severity metrics
  • Expandable AI advice per row
"""
import requests
import pandas as pd
import streamlit as st
st.set_page_config(page_title="Alert History", page_icon="📊", layout="wide")
BACKEND = "http://127.0.0.1:8000"
st.title("📊 Patient Alert History")
st.caption("Clinical alert timeline for individual patients")
def get_patients() -> list:
    try:
        r = requests.get(f"{BACKEND}/patients", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []
def fetch_history(patient_id: str, limit: int) -> list:
    try:
        r = requests.get(
            f"{BACKEND}/history",
            params={"patient_id": patient_id, "limit": limit},
            timeout=5,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        st.error(f"❌ Cannot reach backend: {e}")
    return []
# ── Patient selection ─────────────────────────────────────────────────────────
patients = get_patients()
patient_options = {f"{p['id']} — {p['full_name']}": p["id"] for p in patients}
if not patient_options:
    st.warning("No patients registered. Please register a patient first via **Patient Onboarding**.")
    st.stop()
col1, col2 = st.columns([3, 1])
with col1:
    selected_label = st.selectbox("Select Patient", list(patient_options.keys()))
    selected_id = patient_options[selected_label]
with col2:
    limit = st.number_input("Max records", 10, 200, 50)
if st.button("🔍 Load History", type="primary"):
    st.session_state["history_data"] = fetch_history(selected_id, limit)
    st.session_state["history_patient"] = selected_id
# ── Display ───────────────────────────────────────────────────────────────────
history = st.session_state.get("history_data", [])
current_patient = st.session_state.get("history_patient", "")
if history and current_patient == selected_id:
    df = pd.DataFrame(history)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")
    # Metrics
    st.markdown("---")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Alerts", len(df))
    m2.metric("Critical", int((df["status"] == "CRITICAL").sum()))
    m3.metric("Warning", int((df["status"] == "WARNING").sum()))
    m4.metric("Avg HR (BPM)", f"{df['heart_rate'].mean():.0f}")
    # Heart rate chart
    st.subheader("❤️ Heart Rate Over Time")
    chart_df = df.set_index("timestamp")[["heart_rate"]]
    st.line_chart(chart_df, use_container_width=True)
    # Status distribution
    st.subheader("Alert Severity Distribution")
    status_counts = df["status"].value_counts()
    st.bar_chart(status_counts)
    # Full alert table with expandable AI advice
    st.subheader("Alert Details")
    for _, row in df.iloc[::-1].iterrows():  # newest first
        status_icon = "🔴" if row["status"] == "CRITICAL" else "🟡"
        label = (
            f"{status_icon} {row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} "
            f"| HR: {row['heart_rate']} BPM | {row['status']}"
        )
        with st.expander(label):
            st.markdown(f"**🤖 AI Advice:**\n\n{row['ai_advice']}")
else:
    st.info("Select a patient and click **Load History**.")
