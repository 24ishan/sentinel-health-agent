"""
Live Alerts Page — Real-time incoming clinical alerts from Kafka.
Auto-refreshes every N seconds and color-codes alerts by severity.
"""
import time
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Live Alerts", page_icon="🚨", layout="wide")

BACKEND = "http://127.0.0.1:8000"

st.title("🚨 Live Clinical Alerts")
st.caption("Real-time vitals monitoring via Kafka → FastAPI")

# Friendly column name mapping
COLUMN_LABELS = {
    "timestamp":  "Time",
    "patient_id": "Patient",
    "heart_rate": "Heart Rate (BPM)",
    "status":     "Status",
    "ai_advice":  "AI Advice",
}


def get_patients() -> list:
    try:
        r = requests.get(f"{BACKEND}/patients", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def fetch_alerts(limit: int, patient_id: str = "") -> list:
    try:
        params = {"limit": limit}
        if patient_id:
            params["patient_id"] = patient_id
        resp = requests.get(f"{BACKEND}/history", params=params, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        st.error(f"❌ Cannot reach backend: {e}")
    return []


# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")
    refresh_rate = st.slider("Refresh rate (seconds)", 2, 15, 3)
    limit = st.number_input("Alerts to show", 5, 100, 20)

    patients = get_patients()

    # Build id → name lookup for the table
    id_to_name = {p["id"]: p["full_name"] for p in patients}

    patient_options = {"All Patients": ""} | {
        f"{p['full_name']} ({p['id']})": p["id"] for p in patients
    }
    selected_filter_label = st.selectbox("Filter by Patient", list(patient_options.keys()))
    selected_filter_id = patient_options[selected_filter_label]

    st.markdown("---")
    st.markdown("**Auto-refresh is active.**")


# ── Main loop ─────────────────────────────────────────────────────────────────
placeholder = st.empty()

while True:
    alerts = fetch_alerts(int(limit), selected_filter_id)

    with placeholder.container():
        if alerts:
            latest = alerts[0]
            status_icon = "🔴" if latest["status"] == "CRITICAL" else "🟡" if latest["status"] == "WARNING" else "🟢"
            patient_name = id_to_name.get(latest["patient_id"], latest["patient_id"] or "—")

            # Top metric cards
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Heart Rate (BPM)", latest["heart_rate"])
            m2.metric("Status", f"{status_icon} {latest['status']}")
            m3.metric("Patient", patient_name)
            m4.metric("Total Shown", len(alerts))

            # Latest AI advice
            st.warning(f"**🤖 Latest AI Advice:** {latest['ai_advice']}")

            # Build display dataframe
            st.subheader("Alert Feed")
            df = pd.DataFrame(alerts)
            df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")

            # Replace patient_id with patient name
            df["patient_id"] = df["patient_id"].map(lambda pid: id_to_name.get(pid, pid or "Unknown"))

            # Select and rename columns
            display_cols = list(COLUMN_LABELS.keys())
            df = df[display_cols].rename(columns=COLUMN_LABELS)

            st.dataframe(df.reset_index(drop=True), use_container_width=True, height=400)
        else:
            st.info("⏳ Waiting for alerts from Kafka stream...")

    time.sleep(refresh_rate)
    st.rerun()
