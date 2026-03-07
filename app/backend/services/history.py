"""
Alert history service.

Provides read-only access to persisted ClinicalAlert records, used by
the /history endpoint in the core router.
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.backend.models import ClinicalAlert

class AlertHistory:
    def __init__(self, async_local: sessionmaker):
        """
        Initialize AlertHistory service.

        Args:
            async_local: SQLAlchemy async session factory
        """
        self.session_factory: sessionmaker = async_local

    async def get_alert_history(
            self,
            limit: int = 10,
            patient_id: Optional[str] = None
    ) -> List[ClinicalAlert]:
        """
        Retrieve the most recent clinical alerts.

        Args:
            limit: Maximum number of alerts to return (default: 10, max: 100)
            patient_id: Optional filter to get alerts for specific patient

        Returns:
            List of ClinicalAlert objects ordered by timestamp (newest first)
        """
        async with self.session_factory() as session:
            query = select(ClinicalAlert).order_by(
                ClinicalAlert.timestamp.desc()
            ).limit(min(limit, 100))  # Cap at 100

            if patient_id:
                query = query.where(ClinicalAlert.patient_id == patient_id)

            result = await session.execute(query)
            return result.scalars().all()