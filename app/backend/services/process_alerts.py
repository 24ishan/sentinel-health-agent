from app.backend.models import ClinicalAlert
from app.backend.services.rag_service import MedicalRAG

class ProcessAlerts:
    def __init__(self,AsyncSessionLocal,logger):
        self.AsyncSessionLocal = AsyncSessionLocal
        self.logger = logger
        self.rag_agent = MedicalRAG()

    async def process_critical_alert(self,data, hr):
        try:
            advice = await self.rag_agent.get_clinical_advice(hr)
            print(f"🚨 CRITICAL ALERT: HR {hr} | {advice}")

            async with self.AsyncSessionLocal() as session:
                async with session.begin():
                    new_alert = ClinicalAlert(
                        patient_id=data.get("patient_id"),
                        heart_rate=hr,
                        status="CRITICAL",
                        ai_advice=advice
                    )
                    session.add(new_alert)
            print(f"💾 Alert Saved to DB for HR: {hr}")
        except Exception as e:
            self.logger.error(f"Error processing critical alert: {e}")
