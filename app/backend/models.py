from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import CheckConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

def _utcnow():
    """Timezone-aware UTC datetime — used as SQLAlchemy column defaults."""
    return datetime.now(timezone.utc)
from app.utils.config import (
    POSTGRES_CLINICAL_ALERTS_TABLE,
    POSTGRES_PATIENTS_TABLE,
    POSTGRES_MEDICAL_HISTORY_TABLE,
)

Base = declarative_base()


class Patient(Base):
    """Core patient demographics — PII-sensitive table."""
    __tablename__ = POSTGRES_PATIENTS_TABLE

    id = Column(String, primary_key=True, index=True)          # e.g. "PATIENT_001"
    full_name = Column(String(200), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String(20), nullable=True)
    contact_phone = Column(String(30), nullable=True)
    contact_email = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    medical_history = relationship("MedicalHistory", back_populates="patient", uselist=False)
    alerts = relationship("ClinicalAlert", back_populates="patient")


class MedicalHistory(Base):
    """Separate table for sensitive medical history — isolated for safety."""
    __tablename__ = POSTGRES_MEDICAL_HISTORY_TABLE

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, ForeignKey(f"{POSTGRES_PATIENTS_TABLE}.id"), nullable=False, unique=True)
    allergies = Column(Text, nullable=True)
    current_medications = Column(Text, nullable=True)
    chronic_conditions = Column(Text, nullable=True)
    past_surgeries = Column(Text, nullable=True)
    family_history = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationship
    patient = relationship("Patient", back_populates="medical_history")


class ClinicalAlert(Base):
    """Real-time clinical alerts triggered by abnormal vitals."""
    __tablename__ = POSTGRES_CLINICAL_ALERTS_TABLE
    __table_args__ = (
        CheckConstraint("status IN ('NORMAL', 'WARNING', 'CRITICAL')"),
    )

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, ForeignKey(f"{POSTGRES_PATIENTS_TABLE}.id"), nullable=True)
    heart_rate = Column(Integer)
    status = Column(String)
    ai_advice = Column(Text)
    timestamp = Column(DateTime(timezone=True), default=_utcnow)

    # Relationship
    patient = relationship("Patient", back_populates="alerts")

