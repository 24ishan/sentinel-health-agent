"""
Sentinel Health Agent — Dashboard Home / Landing Page.

Navigate using the sidebar to:
  • Live Alerts       — real-time incoming vital alerts
  • Patient Onboarding — register patients and medical history
  • Alert History     — per-patient alert timeline
  • Nurse Chatbot     — AI-powered clinical consultation
"""

import streamlit as st

st.set_page_config(
    page_title="Sentinel Health Agent",
    page_icon="🏥",
    layout="wide",
)

st.title("🏥 Sentinel Health Agent")
st.markdown("### AI-Powered Clinical Alert Monitoring System")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.info("### 🚨 Live Alerts\nReal-time incoming vitals monitoring from Kafka stream.\n\n👈 Go to **Live Alerts** in the sidebar.")
    st.info("### 📋 Patient Onboarding\nRegister patients with demographics and full medical history.\n\n👈 Go to **Patient Onboarding** in the sidebar.")

with col2:
    st.info("### 📊 Alert History\nView complete alert timeline for any patient.\n\n👈 Go to **Alert History** in the sidebar.")
    st.info("### 💬 Nurse Chatbot\nAsk the AI about any patient — powered by LangGraph + RAG.\n\n👈 Go to **Nurse Chatbot** in the sidebar.")

st.markdown("---")
st.markdown(
    """
    **Stack:** FastAPI · PostgreSQL + pgvector · Apache Kafka · LangGraph · Ollama · Streamlit

    **Features:** Real-time alerts · RAG-enriched AI advice · Patient-aware LLM · MCP tool-calling agent
    """
)
