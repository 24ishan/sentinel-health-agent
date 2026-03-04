import asyncio
from sqlalchemy.orm import sessionmaker
from app.backend.models import ClinicalAlert
from app.backend.services.rag_service import MedicalRAG
from app import setup_logging

logger = setup_logging()

class ProcessAlerts:
    def __init__(self, AsyncSessionLocal: sessionmaker):
        """
        Initialize ProcessAlerts.

        Args:
            AsyncSessionLocal: SQLAlchemy async session factory
        """
        self.AsyncSessionLocal = AsyncSessionLocal
        self._rag_agent: MedicalRAG | None = None

    async def _get_rag_agent(self) -> MedicalRAG:
        """
        Lazy initialization of RAG agent.

        Returns:
            MedicalRAG: Initialized RAG service instance

        Raises:
            RuntimeError: If RAG service initialization fails
        """
        if self._rag_agent is None:
            self._rag_agent = MedicalRAG()
            try:
                await self._rag_agent.initialize()
            except Exception as e:
                logger.error(f"Failed to initialize RAG service: {e}", exc_info=True)
                self._rag_agent = None
                raise
        return self._rag_agent

    async def process_critical_alert(self, data: dict, hr: int) -> dict:
        """Process critical alert and return status.

        Args:
            data: Alert data dict with patient_id
            hr: Heart rate value in BPM

        Returns:
            dict: {"status": "success"|"failed", "message": str}

        Raises:
            ValueError: If inputs invalid
            Exception: If processing fails
        """
        try:
            if not data or not isinstance(data, dict):
                raise ValueError("Alert data must be a valid dict")

            patient_id = data.get("patient_id")
            if not patient_id:
                raise ValueError("patient_id is required")
            if not isinstance(hr, (int, float)) or hr <= 0:
                raise ValueError(f"Invalid heart rate: {hr}")

            # Get RAG agent with lazy initialization
            try:
                rag_agent = await self._get_rag_agent()
            except RuntimeError as e:
                logger.error(f"RAG service unavailable: {e}")
                return {"status": "failed", "reason": "rag_service_unavailable", "message": str(e)}

            advice = await rag_agent.get_clinical_advice(hr)
            logger.debug(f"Starting DB save for patient {patient_id}, HR {hr}, advice: {advice}")
            try:
                async with self.AsyncSessionLocal() as session:
                    async with session.begin():
                        new_alert = ClinicalAlert(
                            patient_id=patient_id,
                            heart_rate=hr,
                            status="CRITICAL",
                            ai_advice=advice
                        )
                        session.add(new_alert)
                logger.info(f"💾 Alert Saved to DB for HR: {hr} | Patient: {patient_id}")
                return {"status": "success", "advice": advice, "saved": True}
            except Exception as db_error:
                logger.error(f"Failed to save alert to DB: {db_error}", exc_info=True)
                return {"status": "partial_success", "advice": advice, "saved_to_db": False, "db_error": str(db_error)}
        except ValueError as e:
            logger.error(f"Invalid input for alert: {e}")
            return {"status": "failed", "reason": "validation_error", "message": str(e)}
        except asyncio.TimeoutError as e:
            logger.error(f"RAG service timeout: {e}")
            return {"status": "failed", "reason": "timeout", "message": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error processing alert: {e}", exc_info=True)
            return {"status": "failed", "reason": "unknown_error", "message": str(e)}
