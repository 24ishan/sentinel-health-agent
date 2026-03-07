"""
SQLAlchemy ORM models for Sentinel Health Agent.

Tables:
  - patients            → Patient demographics (PII-sensitive)
  - medical_history     → Medical history, one-to-one with patients
  - clinical_alerts     → Real-time alerts triggered by abnormal vitals
"""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship

from app.utils.config import (
    POSTGRES_CLINICAL_ALERTS_TABLE,
    POSTGRES_MEDICAL_HISTORY_TABLE,
    POSTGRES_PATIENTS_TABLE,
)


def _utcnow() -> datetime:
    """Return a timezone-aware UTC datetime — used as SQLAlchemy column defaults."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all ORM models (SQLAlchemy 2.x style)."""
    pass


class Patient(Base):
    """Core patient demographics — PII-sensitive table."""

    __tablename__ = POSTGRES_PATIENTS_TABLE

    id = Column(String, primary_key=True, index=True)           # e.g. "PAT-3F2A1B4C"
    full_name = Column(String(200), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String(20), nullable=True)
    contact_phone = Column(String(30), nullable=True)
    contact_email = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # One-to-one with MedicalHistory; one-to-many with ClinicalAlert
    medical_history = relationship("MedicalHistory", back_populates="patient", uselist=False)
    alerts = relationship("ClinicalAlert", back_populates="patient")


class MedicalHistory(Base):
    """Separate table for sensitive medical history — isolated for data safety."""

    __tablename__ = POSTGRES_MEDICAL_HISTORY_TABLE

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(
        String, ForeignKey(f"{POSTGRES_PATIENTS_TABLE}.id"), nullable=False, unique=True
    )
    allergies = Column(Text, nullable=True)
    current_medications = Column(Text, nullable=True)
    chronic_conditions = Column(Text, nullable=True)
    past_surgeries = Column(Text, nullable=True)
    family_history = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    patient = relationship("Patient", back_populates="medical_history")


class ClinicalAlert(Base):
    """Real-time clinical alerts triggered by abnormal vital signs."""

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

    patient = relationship("Patient", back_populates="alerts")

