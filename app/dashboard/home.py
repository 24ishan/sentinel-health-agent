import streamlit as st
import pandas as pd
import requests
import time

st.set_page_config(page_title="AI Clinical Monitor", layout="wide")

st.title("🚨 Real-Time Clinical Alert Dashboard")
st.write("Monitoring Kafka Stream via FastAPI Backend")

# Sidebar for configuration
st.sidebar.header("Settings")
refresh_rate = st.sidebar.slider("Refresh Rate (seconds)", 1, 10, 2)
limit = st.sidebar.number_input("Last N Alerts", 5, 50, 10)

# Placeholder for the data
placeholder = st.empty()


def fetch_data():
    try:
        # We call your working /history API
        response = requests.get(f"http://127.0.0.1:8000/history?limit={limit}")
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"Could not connect to Backend: {e}")
    return []


while True:
    alerts = fetch_data()

    with placeholder.container():
        if alerts:
            df = pd.DataFrame(alerts)

            # Highlight the most recent alert
            latest = alerts[0]
            st.warning(f"**LATEST ALERT:** Patient {latest['patient_id']} - HR: {latest['heart_rate']}")
            st.info(f"**AI Advice:** {latest['ai_advice']}")

            # Show the table of history
            st.subheader("Recent Alert History")
            st.table(df[['timestamp', 'patient_id', 'heart_rate', 'status' , 'ai_advice']])
        else:
            st.write("Searching for clinical alerts...")

    time.sleep(refresh_rate)