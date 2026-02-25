from fastapi import Query
from sqlalchemy import select
from ..models import ClinicalAlert

class AlertHistory:
    def __init__(self,async_local):
        self.async_local = async_local()

    async def get_alert_history(
            self,
            limit: int = Query(default=10, le=100),
            patient_id: str = None
    ):
        """
        Retrieves the most recent clinical alerts.
        Filterable by patient_id for clinical review.
        """
        async with self.async_local as session:
            # Create a base query
            query = select(ClinicalAlert).order_by(ClinicalAlert.timestamp.desc()).limit(limit)

            # Add a filter if patient_id is provided
            if patient_id:
                query = query.where(ClinicalAlert.patient_id == patient_id)

            result = await session.execute(query)
            alerts = result.scalars().all()
            return alerts