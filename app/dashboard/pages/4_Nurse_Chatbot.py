"""
Nurse Chatbot Page — LangGraph-powered clinical AI assistant.

The nurse selects a patient from the dropdown, then chats with the AI.
The AI has MCP tools: get_patient_profile, get_medical_history,
get_recent_alerts, search_medical_knowledge.
"""

import uuid
import requests
import streamlit as st

st.set_page_config(page_title="Nurse Chatbot", page_icon="💬", layout="wide")

BACKEND = "http://127.0.0.1:8000"

st.title("💬 Nurse Chatbot")
st.caption("AI clinical assistant — powered by LangGraph + RAG + MCP tools")


def get_patients() -> list:
    try:
        r = requests.get(f"{BACKEND}/patients", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def send_message(patient_id: str, message: str, session_id: str) -> dict:
    try:
        r = requests.post(
            f"{BACKEND}/chat",
            json={"patient_id": patient_id, "message": message, "session_id": session_id},
            timeout=120,
        )
        if r.status_code == 200:
            return r.json()
        return {"reply": f"Backend error {r.status_code}: {r.text}", "tools_used": None}
    except Exception as e:
        return {"reply": f"Cannot reach backend: {e}", "tools_used": None}


def clear_session(session_id: str):
    try:
        requests.delete(f"{BACKEND}/chat/{session_id}", timeout=5)
    except Exception:
        pass


# ── Session state ─────────────────────────────────────────────────────────────
if "chat_session_id" not in st.session_state:
    st.session_state.chat_session_id = str(uuid.uuid4())
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "chat_patient_id" not in st.session_state:
    st.session_state.chat_patient_id = None

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🧑‍⚕️ Session")

    patients = get_patients()
    patient_options = {f"{p['full_name']} ({p['id']})": p["id"] for p in patients}

    if not patient_options:
        st.warning("No patients registered. Go to Patient Onboarding first.")
        st.stop()

    selected_label = st.selectbox("Patient you're consulting about:", list(patient_options.keys()))
    selected_id = patient_options[selected_label]

    # Reset conversation when patient changes
    if st.session_state.chat_patient_id != selected_id:
        clear_session(st.session_state.chat_session_id)
        st.session_state.chat_session_id = str(uuid.uuid4())
        st.session_state.chat_messages = []
        st.session_state.chat_patient_id = selected_id

    st.markdown(f"**Session:** `{st.session_state.chat_session_id[:8]}...`")

    if st.button("🗑️ Clear Conversation"):
        clear_session(st.session_state.chat_session_id)
        st.session_state.chat_session_id = str(uuid.uuid4())
        st.session_state.chat_messages = []
        st.rerun()

    st.markdown("---")
    st.markdown("**AI Tools Available:**")
    st.markdown("- 👤 Patient profile")
    st.markdown("- 🏥 Medical history")
    st.markdown("- 🚨 Recent alerts")
    st.markdown("- 📚 Clinical knowledge base")

# ── Chat area ─────────────────────────────────────────────────────────────────
st.markdown(f"**Consulting about:** {selected_label}")
st.markdown("---")

# Render existing conversation
for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("tools_used"):
            with st.expander("🔧 Tools used by AI", expanded=False):
                for tool in msg["tools_used"]:
                    st.markdown(f"- `{tool}`")

# ── Input ─────────────────────────────────────────────────────────────────────
prompt = st.chat_input("Ask about this patient...")

if prompt:
    # Show nurse message immediately
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Call backend and show response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = send_message(selected_id, prompt, st.session_state.chat_session_id)

        reply = response.get("reply", "Sorry, I could not process that.")
        tools_used = response.get("tools_used")

        st.markdown(reply)

        if tools_used:
            with st.expander("🔧 Tools used by AI", expanded=False):
                for tool in tools_used:
                    st.markdown(f"- `{tool}`")

    # Save to history
    st.session_state.chat_messages.append({
        "role": "assistant",
        "content": reply,
        "tools_used": tools_used,
    })
