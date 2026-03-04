from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional

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

class UploadResponse(BaseModel):
    """Response for PDF upload endpoint."""
    message: str = Field(..., description="Success/status message")
    status: str = Field(..., description="Current status")
    job_id: str = Field(..., description="Unique job identifier")

class HealthCheckResponse(BaseModel):
    """Response for health check endpoint."""
    status: str = Field(..., description="Overall health status")
    kafka_connected: Optional[bool] = Field(None, description="Kafka connection status")
    kafka_task_running: Optional[bool] = Field(None, description="Kafka task status")
    timestamp: str = Field(..., description="Check timestamp")

class RAGHealthResponse(BaseModel):
    """Response for RAG service health check."""
    status: str = Field(..., description="Service status: healthy/degraded/unhealthy")
    embedding_model: Optional[bool] = Field(None, description="Embeddings model status")
    vector_store: Optional[bool] = Field(None, description="Vector store status")
    llm_model: Optional[bool] = Field(None, description="LLM model status")
    timestamp: str = Field(..., description="Check timestamp")
    errors: Optional[list] = Field(None, description="List of errors if any")