"""
Pydantic request / response schemas for the Sentinel Health Agent API.

Grouped by domain:
  - Alert schemas      → ClinicalAlertResponse, HealthCheckResponse, RAGHealthResponse
  - Upload schemas     → UploadResponse
  - Patient schemas    → PatientCreate, PatientUpdate, PatientResponse
  - History schemas    → MedicalHistoryCreate, MedicalHistoryResponse
  - Chatbot schemas    → ChatRequest, ChatResponse
"""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ─────────────────────────────────────────────
# Existing Alert Schemas
# ─────────────────────────────────────────────

class ClinicalAlertResponse(BaseModel):
    id: int
    patient_id: Optional[str] = None
    heart_rate: int
    status: str
    ai_advice: str
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)

class UploadResponse(BaseModel):
    message: str = Field(..., description="Success/status message")
    status: str = Field(..., description="Current status")
    job_id: str = Field(..., description="Unique job identifier")

class HealthCheckResponse(BaseModel):
    status: str = Field(..., description="Overall health status")
    kafka_connected: Optional[bool] = Field(None)
    kafka_task_running: Optional[bool] = Field(None)
    timestamp: str = Field(..., description="Check timestamp")

class RAGHealthResponse(BaseModel):
    status: str = Field(..., description="Service status: healthy/degraded/unhealthy")
    embedding_model: Optional[bool] = Field(None)
    vector_store: Optional[bool] = Field(None)
    llm_model: Optional[bool] = Field(None)
    timestamp: str = Field(..., description="Check timestamp")
    errors: Optional[list] = Field(None)

# ─────────────────────────────────────────────
# Patient Schemas
# ─────────────────────────────────────────────

class PatientCreate(BaseModel):
    """Schema for registering a new patient."""
    full_name: str = Field(..., description="Patient's full name", min_length=2)
    date_of_birth: Optional[date] = Field(None, description="Date of birth YYYY-MM-DD")
    gender: Optional[str] = Field(None, description="Gender identity")
    contact_phone: Optional[str] = Field(None, description="Contact phone number")
    contact_email: Optional[str] = Field(None, description="Contact email address")

class PatientUpdate(BaseModel):
    """Schema for updating an existing patient's basic info."""
    full_name: Optional[str] = Field(None, min_length=2)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None

class PatientResponse(BaseModel):
    id: str
    full_name: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

# ─────────────────────────────────────────────
# Medical History Schemas
# ─────────────────────────────────────────────

class MedicalHistoryCreate(BaseModel):
    """Schema for saving / updating a patient's medical history."""
    allergies: Optional[str] = Field(None, description="Known allergies, comma-separated")
    current_medications: Optional[str] = Field(None, description="Current medications")
    chronic_conditions: Optional[str] = Field(None, description="Chronic conditions e.g. Diabetes, Hypertension")
    past_surgeries: Optional[str] = Field(None, description="Past surgical history")
    family_history: Optional[str] = Field(None, description="Relevant family medical history")
    notes: Optional[str] = Field(None, description="Additional clinical notes")

class MedicalHistoryResponse(BaseModel):
    id: int
    patient_id: str
    allergies: Optional[str] = None
    current_medications: Optional[str] = None
    chronic_conditions: Optional[str] = None
    past_surgeries: Optional[str] = None
    family_history: Optional[str] = None
    notes: Optional[str] = None
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

# ─────────────────────────────────────────────
# Chatbot Schemas
# ─────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Nurse chatbot request."""
    patient_id: str = Field(..., description="Patient the nurse is consulting about")
    message: str = Field(..., description="Nurse's message / question", min_length=1)
    session_id: str = Field(..., description="Unique session ID for conversation memory")

class ChatResponse(BaseModel):
    """Chatbot response with optional tool usage transparency."""
    reply: str = Field(..., description="LLM response to the nurse")
    patient_id: str
    session_id: str
    tools_used: Optional[List[str]] = Field(None, description="MCP tools invoked during this turn")
