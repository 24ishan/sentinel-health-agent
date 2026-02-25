from pydantic import BaseModel, ConfigDict
from datetime import datetime

class ClinicalAlertResponse(BaseModel):
    # This must match your SQLAlchemy model field names
    id: int
    patient_id: str
    heart_rate: int
    status: str
    ai_advice: str
    timestamp: datetime

    # This is the "Magic" part for SQLAlchemy
    model_config = ConfigDict(from_attributes=True)