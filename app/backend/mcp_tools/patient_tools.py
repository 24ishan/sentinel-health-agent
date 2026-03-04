"""
MCP-style tools for the Nurse Chatbot LangGraph agent.
Each function is decorated with @tool from langchain_core, making it
self-describing (name + docstring + type hints → JSON schema) and
callable by the LLM automatically via LangGraph's ToolNode.
These tools act as the "MCP server" interface — the LangGraph agent
autonomously decides which tools to call based on the nurse's question.
"""
from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app import setup_logging
logger = setup_logging()
def build_patient_tools(session: AsyncSession, rag_service=None):
    """
    Factory that builds LangChain tools with injected DB session + RAG.
    Using a factory pattern because async tools need access to runtime
    resources (DB session, RAG service) that aren't available at import time.
    Args:
        session: Active async SQLAlchemy session
        rag_service: Initialized MedicalRAG instance (optional)
    Returns:
        list: LangChain @tool decorated async functions ready for LangGraph
    """
    @tool
    async def get_patient_profile(patient_id: str) -> str:
        """
        Retrieve the basic demographic profile of a patient.
        Use this to get the patient's name, gender, date of birth, and contact info.
        Args:
            patient_id: The patient's unique identifier e.g. PATIENT_001
        """
        from app.backend.models import Patient
        try:
            patient = await session.get(Patient, patient_id)
            if not patient:
                return f"No patient found with ID '{patient_id}'."
            return (
                f"Patient Profile:\n"
                f"  ID: {patient.id}\n"
                f"  Name: {patient.full_name}\n"
                f"  DOB: {patient.date_of_birth}\n"
                f"  Gender: {patient.gender or 'Not specified'}\n"
                f"  Phone: {patient.contact_phone or 'Not provided'}\n"
                f"  Email: {patient.contact_email or 'Not provided'}"
            )
        except Exception as e:
            logger.error(f"get_patient_profile error: {e}")
            return f"Error retrieving patient profile: {str(e)}"
    @tool
    async def get_medical_history(patient_id: str) -> str:
        """
        Retrieve the complete medical history of a patient.
        Returns allergies, current medications, chronic conditions,
        past surgeries, family history, and clinical notes.
        Args:
            patient_id: The patient's unique identifier e.g. PATIENT_001
        """
        from app.backend.models import MedicalHistory
        try:
            result = await session.execute(
                select(MedicalHistory).where(MedicalHistory.patient_id == patient_id)
            )
            history = result.scalar_one_or_none()
            if not history:
                return f"No medical history on record for patient '{patient_id}'."
            return (
                f"Medical History for {patient_id}:\n"
                f"  Allergies: {history.allergies or 'None known'}\n"
                f"  Current Medications: {history.current_medications or 'None'}\n"
                f"  Chronic Conditions: {history.chronic_conditions or 'None'}\n"
                f"  Past Surgeries: {history.past_surgeries or 'None'}\n"
                f"  Family History: {history.family_history or 'None'}\n"
                f"  Notes: {history.notes or 'None'}"
            )
        except Exception as e:
            logger.error(f"get_medical_history error: {e}")
            return f"Error retrieving medical history: {str(e)}"
    @tool
    async def get_recent_alerts(patient_id: str, limit: int = 5) -> str:
        """
        Retrieve recent clinical alerts for a patient, ordered newest first.
        Use this to understand recent vital sign events and the AI advice given.
        Args:
            patient_id: The patient's unique identifier e.g. PATIENT_001
            limit: Number of recent alerts to retrieve (default 5, max 20)
        """
        from app.backend.models import ClinicalAlert
        try:
            limit = min(limit, 20)
            result = await session.execute(
                select(ClinicalAlert)
                .where(ClinicalAlert.patient_id == patient_id)
                .order_by(ClinicalAlert.timestamp.desc())
                .limit(limit)
            )
            alerts = result.scalars().all()
            if not alerts:
                return f"No alerts found for patient '{patient_id}'."
            lines = [f"Recent {len(alerts)} alert(s) for {patient_id}:"]
            for a in alerts:
                lines.append(
                    f"  [{a.timestamp.strftime('%Y-%m-%d %H:%M')}] "
                    f"Status: {a.status} | HR: {a.heart_rate} BPM | "
                    f"AI Advice: {a.ai_advice}"
                )
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"get_recent_alerts error: {e}")
            return f"Error retrieving alerts: {str(e)}"
    @tool
    async def search_medical_knowledge(query: str) -> str:
        """
        Search the medical knowledge base (clinical guidelines, uploaded PDFs)
        for evidence-based information on a condition, treatment, or vital sign.
        Args:
            query: Clinical question e.g. 'tachycardia treatment guidelines'
        """
        if rag_service is None:
            return "Medical knowledge base is currently unavailable."
        try:
            store = await rag_service._get_store()
            docs = await store.asimilarity_search(query, k=3)
            if not docs:
                return "No relevant clinical guidelines found for this query."
            context = "\n---\n".join([doc.page_content for doc in docs])
            return f"Clinical Knowledge Base Results:\n{context[:2000]}"
        except Exception as e:
            logger.error(f"search_medical_knowledge error: {e}")
            return f"Error searching knowledge base: {str(e)}"
    return [
        get_patient_profile,
        get_medical_history,
        get_recent_alerts,
        search_medical_knowledge,
    ]
