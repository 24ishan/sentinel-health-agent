import asyncio
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from app.backend.models import ClinicalAlert, Patient, MedicalHistory
from app.backend.services.rag_service import MedicalRAG
from app.backend.services.prompts import ClinicalPrompts
from app import setup_logging

logger = setup_logging()


class ProcessAlerts:
    def __init__(self, AsyncSessionLocal: sessionmaker, rag_service=None):
        """
        Initialize ProcessAlerts.

        Args:
            AsyncSessionLocal: SQLAlchemy async session factory
            rag_service: Pre-initialized MedicalRAG instance (optional, lazy-init fallback)
        """
        self.AsyncSessionLocal = AsyncSessionLocal
        self._rag_agent: MedicalRAG | None = rag_service

    async def _get_rag_agent(self) -> MedicalRAG:
        """Lazy initialization of RAG agent if not injected."""
        if self._rag_agent is None:
            self._rag_agent = MedicalRAG()
            try:
                await self._rag_agent.initialize()
            except Exception as e:
                logger.error(f"Failed to initialize RAG service: {e}", exc_info=True)
                self._rag_agent = None
                raise
        return self._rag_agent

    async def _fetch_patient_context(self, session, patient_id: str) -> dict:
        """
        Fetch patient demographics and medical history for enriched LLM prompting.

        Args:
            session: Active async SQLAlchemy session
            patient_id: The patient ID to look up

        Returns:
            dict with patient profile fields (empty strings if not found)
        """
        defaults = {
            "patient_name": "Unknown",
            "gender": "Not specified",
            "dob": "Unknown",
            "allergies": "None known",
            "current_medications": "None",
            "chronic_conditions": "None",
            "notes": "None",
        }
        try:
            patient = await session.get(Patient, patient_id)
            if patient:
                defaults["patient_name"] = patient.full_name
                defaults["gender"] = patient.gender or "Not specified"
                defaults["dob"] = str(patient.date_of_birth) if patient.date_of_birth else "Unknown"

            result = await session.execute(
                select(MedicalHistory).where(MedicalHistory.patient_id == patient_id)
            )
            history = result.scalar_one_or_none()
            if history:
                defaults["allergies"] = history.allergies or "None known"
                defaults["current_medications"] = history.current_medications or "None"
                defaults["chronic_conditions"] = history.chronic_conditions or "None"
                defaults["notes"] = history.notes or "None"

        except Exception as e:
            logger.warning(f"Could not fetch patient context for {patient_id}: {e}")

        return defaults

    async def process_critical_alert(self, data: dict, hr: int) -> dict:
        """
        Process a critical/warning alert.

        Pipeline:
          1. Validate inputs
          2. Fetch patient demographics + medical history from DB
          3. Query RAG for relevant clinical guidelines
          4. Build enriched prompt and call LLM
          5. Save alert with AI advice to DB

        Args:
            data: Alert data dict with at minimum 'patient_id' and 'status'
            hr: Heart rate value in BPM

        Returns:
            dict: {"status": "success"|"failed"|"partial_success", ...}
        """
        try:
            if not data or not isinstance(data, dict):
                raise ValueError("Alert data must be a valid dict")

            patient_id = data.get("patient_id")
            if not patient_id:
                raise ValueError("patient_id is required")
            if not isinstance(hr, (int, float)) or hr <= 0:
                raise ValueError(f"Invalid heart rate: {hr}")

            # Get RAG agent
            try:
                rag_agent = await self._get_rag_agent()
            except RuntimeError as e:
                logger.error(f"RAG service unavailable: {e}")
                return {"status": "failed", "reason": "rag_service_unavailable", "message": str(e)}

            async with self.AsyncSessionLocal() as session:
                # Fetch patient context for enriched prompt
                patient_ctx = await self._fetch_patient_context(session, patient_id)

                # Get RAG clinical context
                store = await rag_agent._get_store()
                query = f"Clinical guidelines for heart rate of {hr} BPM"
                docs = await store.asimilarity_search(query, k=2)
                context = "\n".join([doc.page_content for doc in docs]) if docs else ""

                # Build enriched prompt with patient context
                if context:
                    full_prompt = ClinicalPrompts.get_enriched_advice_prompt(
                        context=context,
                        heart_rate=hr,
                        **patient_ctx,
                    )
                else:
                    full_prompt = ClinicalPrompts.get_clinical_advice_prompt(
                        context="No clinical guidelines available.",
                        heart_rate=hr,
                    )

                advice = await rag_agent._call_ollama_llm(full_prompt)

                logger.debug(
                    f"Saving alert for patient {patient_id} "
                    f"| HR: {hr} | Context used: {bool(context)}"
                )

                # Save alert to DB
                try:
                    new_alert = ClinicalAlert(
                        patient_id=patient_id,
                        heart_rate=hr,
                        status=data.get("status", "CRITICAL"),
                        ai_advice=advice,
                    )
                    session.add(new_alert)
                    await session.commit()
                    logger.info(
                        f"💾 Alert saved | Patient: {patient_id} "
                        f"| HR: {hr} | Status: {data.get('status')}"
                    )
                    return {"status": "success", "advice": advice, "saved": True}

                except Exception as db_error:
                    logger.error(f"Failed to save alert to DB: {db_error}", exc_info=True)
                    return {
                        "status": "partial_success",
                        "advice": advice,
                        "saved_to_db": False,
                        "db_error": str(db_error),
                    }

        except ValueError as e:
            logger.error(f"Invalid input for alert: {e}")
            return {"status": "failed", "reason": "validation_error", "message": str(e)}
        except asyncio.TimeoutError as e:
            logger.error(f"RAG service timeout: {e}")
            return {"status": "failed", "reason": "timeout", "message": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error processing alert: {e}", exc_info=True)
            return {"status": "failed", "reason": "unknown_error", "message": str(e)}
