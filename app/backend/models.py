from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class ClinicalAlert(Base):
    __tablename__ = "clinical_alerts"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String)
    heart_rate = Column(Integer)
    status = Column(String)
    ai_advice = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)