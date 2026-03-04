"""
Patient Onboarding Page.

Tab 1: Register a new patient (demographics → POST /patients)
Tab 2: Add / update medical history (→ POST /patients/{id}/history)
Tab 3: View registered patients list
"""

import datetime
import requests
import streamlit as st

st.set_page_config(page_title="Patient Onboarding", page_icon="📋", layout="wide")

BACKEND = "http://127.0.0.1:8000"

st.title("📋 Patient Onboarding")
st.caption("Register patients and maintain their medical history")

TODAY = datetime.date.today()
MIN_DOB = datetime.date(1900, 1, 1)
MAX_DOB = TODAY   # Cannot register a future DOB


def get_patients() -> list:
    try:
        r = requests.get(f"{BACKEND}/patients", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


tab1, tab2, tab3 = st.tabs(["➕ Register Patient", "🏥 Medical History", "👥 All Patients"])


# ── Tab 1: Register Patient ───────────────────────────────────────────────────
with tab1:
    st.subheader("Register New Patient")
    st.markdown("*Patient ID is generated automatically. Basic demographics are stored separately from medical history for data safety.*")

    with st.form("register_patient_form"):
        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("Full Name *", placeholder="Jane Doe")
            dob = st.date_input(
                "Date of Birth",
                value=None,
                min_value=MIN_DOB,
                max_value=MAX_DOB,
            )
        with col2:
            gender = st.selectbox("Gender", ["", "Male", "Female", "Non-binary", "Prefer not to say"])
            phone = st.text_input("Contact Phone", placeholder="+1-555-0000")
        email = st.text_input("Contact Email", placeholder="patient@example.com")

        submitted = st.form_submit_button("✅ Register Patient", type="primary")
        if submitted:
            if not full_name.strip():
                st.error("Full Name is required.")
            else:
                payload = {
                    "full_name": full_name.strip(),
                    "gender": gender or None,
                    "contact_phone": phone or None,
                    "contact_email": email or None,
                }
                if dob:
                    payload["date_of_birth"] = str(dob)
                try:
                    r = requests.post(f"{BACKEND}/patients", json=payload, timeout=10)
                    if r.status_code == 201:
                        data = r.json()
                        st.success(f"✅ Patient **{full_name}** registered successfully!")
                        st.info(f"🪪 Auto-generated Patient ID: **`{data['id']}`** — save this for reference.")
                        st.json(data)
                    else:
                        st.error(f"❌ Error: {r.status_code} — {r.text}")
                except Exception as e:
                    st.error(f"❌ Cannot reach backend: {e}")


# ── Tab 2: Medical History ────────────────────────────────────────────────────
with tab2:
    st.subheader("Add / Update Medical History")
    st.markdown("*Medical history is stored in a separate table for patient data safety.*")

    patients = get_patients()
    patient_options = {f"{p['full_name']} ({p['id']})": p["id"] for p in patients}

    if not patient_options:
        st.info("No patients registered yet. Register a patient in the first tab.")
    else:
        selected_label = st.selectbox("Select Patient", list(patient_options.keys()))
        selected_id = patient_options[selected_label]

        # Pre-fill if history exists
        existing = {}
        try:
            r = requests.get(f"{BACKEND}/patients/{selected_id}/history", timeout=5)
            if r.status_code == 200:
                existing = r.json()
                st.info("ℹ️ Existing history found — editing it now.")
        except Exception:
            pass

        with st.form("medical_history_form"):
            allergies = st.text_area(
                "Allergies",
                value=existing.get("allergies", ""),
                placeholder="e.g. Penicillin, Sulfa drugs, Latex",
            )
            medications = st.text_area(
                "Current Medications",
                value=existing.get("current_medications", ""),
                placeholder="e.g. Metoprolol 50mg daily, Aspirin 81mg daily",
            )
            conditions = st.text_area(
                "Chronic Conditions",
                value=existing.get("chronic_conditions", ""),
                placeholder="e.g. Hypertension, Type 2 Diabetes, COPD",
            )
            surgeries = st.text_area(
                "Past Surgeries",
                value=existing.get("past_surgeries", ""),
                placeholder="e.g. Appendectomy 2018, CABG 2020",
            )
            family_hx = st.text_area(
                "Family History",
                value=existing.get("family_history", ""),
                placeholder="e.g. Father: MI at 55, Mother: Hypertension",
            )
            notes = st.text_area(
                "Clinical Notes",
                value=existing.get("notes", ""),
                placeholder="Any additional clinical notes...",
            )

            save = st.form_submit_button("💾 Save Medical History", type="primary")
            if save:
                payload = {
                    "allergies": allergies or None,
                    "current_medications": medications or None,
                    "chronic_conditions": conditions or None,
                    "past_surgeries": surgeries or None,
                    "family_history": family_hx or None,
                    "notes": notes or None,
                }
                try:
                    r = requests.post(
                        f"{BACKEND}/patients/{selected_id}/history",
                        json=payload,
                        timeout=10,
                    )
                    if r.status_code in (200, 201):
                        st.success(f"✅ Medical history saved for **{selected_label}**!")
                    else:
                        st.error(f"❌ Error {r.status_code}: {r.text}")
                except Exception as e:
                    st.error(f"❌ Cannot reach backend: {e}")


# ── Tab 3: All Patients ───────────────────────────────────────────────────────
with tab3:
    st.subheader("Registered Patients")
    if st.button("🔄 Refresh List"):
        st.rerun()

    patients = get_patients()
    if patients:
        st.metric("Total Patients", len(patients))
        for p in patients:
            with st.expander(f"**{p['full_name']}** — `{p['id']}`"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**DOB:** {p.get('date_of_birth') or '—'}")
                    st.write(f"**Gender:** {p.get('gender') or '—'}")
                with col2:
                    st.write(f"**Phone:** {p.get('contact_phone') or '—'}")
                    st.write(f"**Email:** {p.get('contact_email') or '—'}")
                    st.write(f"**Registered:** {p.get('created_at', '')[:10]}")
    else:
        st.info("No patients registered yet.")
