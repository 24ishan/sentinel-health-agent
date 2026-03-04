"""
Patient management API router.

Handles CRUD for Patient demographics and Medical History records.
These are split into two separate tables intentionally for data safety.
"""

from datetime import datetime, timezone
from typing import List
import uuid

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import setup_logging
from app.backend.models import Patient, MedicalHistory
from app.backend.schemas import (
    PatientCreate,
    PatientUpdate,
    PatientResponse,
    MedicalHistoryCreate,
    MedicalHistoryResponse,
)

logger = setup_logging()

router = APIRouter(prefix="/patients", tags=["Patients"])


# ─────────────────────────────────────────────────────────────
# Patient CRUD
# ─────────────────────────────────────────────────────────────

@router.post("", response_model=PatientResponse, status_code=201)
async def register_patient(payload: PatientCreate, request: Request):
    """Register a new patient. ID is auto-generated as a UUID."""
    async with request.app.state.session_factory() as session:
        patient_id = f"PAT-{uuid.uuid4().hex[:8].upper()}"   # e.g. PAT-3F2A1B4C
        patient = Patient(id=patient_id, **payload.model_dump())
        session.add(patient)
        await session.commit()
        await session.refresh(patient)
        logger.info(f"✅ Registered new patient: {patient.id} — {patient.full_name}")
        return patient


@router.get("", response_model=List[PatientResponse])
async def list_patients(request: Request):
    """Return all registered patients."""
    async with request.app.state.session_factory() as session:
        result = await session.execute(select(Patient).order_by(Patient.full_name))
        return result.scalars().all()


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(patient_id: str, request: Request):
    """Fetch a single patient by ID."""
    async with request.app.state.session_factory() as session:
        patient = await session.get(Patient, patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient '{patient_id}' not found.")
        return patient


@router.put("/{patient_id}", response_model=PatientResponse)
async def update_patient(patient_id: str, payload: PatientUpdate, request: Request):
    """Update a patient's basic demographic info."""
    async with request.app.state.session_factory() as session:
        patient = await session.get(Patient, patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient '{patient_id}' not found.")

        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(patient, field, value)
        patient.updated_at = datetime.now(timezone.utc)

        await session.commit()
        await session.refresh(patient)
        logger.info(f"✅ Updated patient: {patient_id}")
        return patient


# ─────────────────────────────────────────────────────────────
# Medical History (separate table — isolated for data safety)
# ─────────────────────────────────────────────────────────────

@router.post("/{patient_id}/history", response_model=MedicalHistoryResponse, status_code=201)
async def upsert_medical_history(patient_id: str, payload: MedicalHistoryCreate, request: Request):
    """
    Create or update medical history for a patient.
    Uses upsert semantics — safe to call multiple times.
    """
    async with request.app.state.session_factory() as session:
        # Ensure patient exists
        patient = await session.get(Patient, patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient '{patient_id}' not found.")

        result = await session.execute(
            select(MedicalHistory).where(MedicalHistory.patient_id == patient_id)
        )
        history = result.scalar_one_or_none()

        if history:
            for field, value in payload.model_dump(exclude_none=True).items():
                setattr(history, field, value)
            history.updated_at = datetime.now(timezone.utc)
            logger.info(f"🔄 Updated medical history for patient: {patient_id}")
        else:
            history = MedicalHistory(patient_id=patient_id, **payload.model_dump())
            session.add(history)
            logger.info(f"✅ Created medical history for patient: {patient_id}")

        await session.commit()
        await session.refresh(history)
        return history


@router.get("/{patient_id}/history", response_model=MedicalHistoryResponse)
async def get_medical_history(patient_id: str, request: Request):
    """Retrieve a patient's medical history."""
    async with request.app.state.session_factory() as session:
        result = await session.execute(
            select(MedicalHistory).where(MedicalHistory.patient_id == patient_id)
        )
        history = result.scalar_one_or_none()
        if not history:
            raise HTTPException(
                status_code=404,
                detail=f"No medical history found for patient '{patient_id}'."
            )
        return history








