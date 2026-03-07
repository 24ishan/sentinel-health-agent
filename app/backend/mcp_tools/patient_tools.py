"""
MCP-style tools for the Nurse Chatbot LangGraph agent.

Each tool is a method on `PatientToolkit` wrapped with LangChain's
`StructuredTool.from_function` so the LLM receives a proper JSON schema
for each tool.  The class pattern replaces the previous factory function
with nested `@tool` closures, making the code testable and class-scoped.

Usage:
    toolkit = PatientToolkit(session, rag_service)
    tools   = toolkit.get_tools()   # pass to ChatbotGraphBuilder(tools).build()
"""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import setup_logging

logger = setup_logging()


# ---------------------------------------------------------------------------
# Pydantic input schemas — give the LLM precise JSON schemas for each tool
# ---------------------------------------------------------------------------

class PatientIdInput(BaseModel):
    """Input schema for tools that take only a patient ID."""
    patient_id: str = Field(..., description="The patient's unique identifier e.g. PATIENT_001")


class RecentAlertsInput(BaseModel):
    """Input schema for get_recent_alerts."""
    patient_id: str = Field(..., description="The patient's unique identifier e.g. PATIENT_001")
    limit: int = Field(5, description="Number of recent alerts to retrieve (default 5, max 20)")


class MedicalKnowledgeInput(BaseModel):
    """Input schema for search_medical_knowledge."""
    query: str = Field(..., description="Clinical question e.g. 'tachycardia treatment guidelines'")


# ---------------------------------------------------------------------------
# Patient toolkit
# ---------------------------------------------------------------------------

class PatientToolkit:
    """
    Provides LangChain tools that give the nurse chatbot access to patient
    data (DB) and the medical knowledge base (RAG vector store).

    Each private `_tool_*` method implements the tool logic.
    `get_tools()` wraps them with `StructuredTool.from_function` so
    LangGraph's ToolNode can execute them automatically.

    Args:
        session:     Active async SQLAlchemy session scoped to the request.
        rag_service: Initialised MedicalRAG instance (optional — tools
                     degrade gracefully when RAG is unavailable).
    """

    def __init__(self, session: AsyncSession, rag_service=None) -> None:
        self._session = session
        self._rag = rag_service

    # ── Tool implementations ─────────────────────────────────────────────

    async def _tool_get_patient_profile(self, patient_id: str) -> str:
        """
        Retrieve the basic demographic profile of a patient.
        Use this to get the patient's name, gender, date of birth, and contact info.
        """
        from app.backend.models import Patient

        try:
            patient = await self._session.get(Patient, patient_id)
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
        except Exception as exc:
            logger.error(f"get_patient_profile error: {exc}")
            return f"Error retrieving patient profile: {exc}"

    async def _tool_get_medical_history(self, patient_id: str) -> str:
        """
        Retrieve the complete medical history of a patient.
        Returns allergies, current medications, chronic conditions,
        past surgeries, family history, and clinical notes.
        """
        from app.backend.models import MedicalHistory

        try:
            result = await self._session.execute(
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
        except Exception as exc:
            logger.error(f"get_medical_history error: {exc}")
            return f"Error retrieving medical history: {exc}"

    async def _tool_get_recent_alerts(self, patient_id: str, limit: int = 5) -> str:
        """
        Retrieve recent clinical alerts for a patient, ordered newest first.
        Use this to understand recent vital sign events and the AI advice given.
        """
        from app.backend.models import ClinicalAlert

        try:
            limit = min(limit, 20)  # Hard cap to prevent abuse
            result = await self._session.execute(
                select(ClinicalAlert)
                .where(ClinicalAlert.patient_id == patient_id)
                .order_by(ClinicalAlert.timestamp.desc())
                .limit(limit)
            )
            alerts = result.scalars().all()
            if not alerts:
                return f"No alerts found for patient '{patient_id}'."
            lines = [f"Recent {len(alerts)} alert(s) for {patient_id}:"]
            for alert in alerts:
                lines.append(
                    f"  [{alert.timestamp.strftime('%Y-%m-%d %H:%M')}] "
                    f"Status: {alert.status} | HR: {alert.heart_rate} BPM | "
                    f"AI Advice: {alert.ai_advice}"
                )
            return "\n".join(lines)
        except Exception as exc:
            logger.error(f"get_recent_alerts error: {exc}")
            return f"Error retrieving alerts: {exc}"

    async def _tool_search_medical_knowledge(self, query: str) -> str:
        """
        Search the medical knowledge base (clinical guidelines, uploaded PDFs)
        for evidence-based information on a condition, treatment, or vital sign.
        """
        if self._rag is None:
            return "Medical knowledge base is currently unavailable."
        try:
            store = await self._rag._get_store()
            docs = await store.asimilarity_search(query, k=3)
            if not docs:
                return "No relevant clinical guidelines found for this query."
            # Limit response to 2000 characters to keep the LLM prompt manageable
            context = "\n---\n".join([doc.page_content for doc in docs])
            return f"Clinical Knowledge Base Results:\n{context[:2000]}"
        except Exception as exc:
            logger.error(f"search_medical_knowledge error: {exc}")
            return f"Error searching knowledge base: {exc}"

    # ── Public API ────────────────────────────────────────────────────────

    def get_tools(self) -> list:
        """
        Return all tools as LangChain StructuredTool instances.

        StructuredTool.from_function wraps each async coroutine method
        with the correct Pydantic schema so the LLM receives a well-typed
        JSON schema — this is required because @tool does not work natively
        on instance methods (self would leak into the tool schema).

        Returns:
            list: Ready-to-use LangChain tools for LangGraph's ToolNode.
        """
        return [
            StructuredTool.from_function(
                coroutine=self._tool_get_patient_profile,
                name="get_patient_profile",
                description=(
                    "Retrieve the basic demographic profile of a patient. "
                    "Use this to get the patient's name, gender, date of birth, and contact info."
                ),
                args_schema=PatientIdInput,
            ),
            StructuredTool.from_function(
                coroutine=self._tool_get_medical_history,
                name="get_medical_history",
                description=(
                    "Retrieve the complete medical history of a patient. "
                    "Returns allergies, current medications, chronic conditions, "
                    "past surgeries, family history, and clinical notes."
                ),
                args_schema=PatientIdInput,
            ),
            StructuredTool.from_function(
                coroutine=self._tool_get_recent_alerts,
                name="get_recent_alerts",
                description=(
                    "Retrieve recent clinical alerts for a patient, ordered newest first. "
                    "Use this to understand recent vital sign events and the AI advice given."
                ),
                args_schema=RecentAlertsInput,
            ),
            StructuredTool.from_function(
                coroutine=self._tool_search_medical_knowledge,
                name="search_medical_knowledge",
                description=(
                    "Search the medical knowledge base (clinical guidelines, uploaded PDFs) "
                    "for evidence-based information on a condition, treatment, or vital sign."
                ),
                args_schema=MedicalKnowledgeInput,
            ),
        ]

