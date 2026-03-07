"""
Core API router — health checks, alert history, document upload.

Endpoints that are not patient-CRUD or chatbot-specific live here.
All routes are registered on `router`; `main.py` mounts it via
`app.include_router(core_router.router)`.
"""
import os
import shutil
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile

from app import setup_logging
from app.backend.database import engine
from app.backend.schemas import ClinicalAlertResponse, UploadResponse
from app.backend.services.history import AlertHistory
from app.utils.config import OLLAMA_HOST, VECTOR_TABLE_NAME
from app.vector_db.ingest_pdf import PostgresRAGManager

logger = setup_logging()

router = APIRouter(tags=["Core"])


# ---------------------------------------------------------------------------
# Helper — runs in a FastAPI background task after a PDF upload
# ---------------------------------------------------------------------------

async def _run_indexing(file_path: str) -> None:
    """
    Index a PDF file into the vector store, then clean up the temp file.

    This function is intentionally module-level (not a closure) so it can
    be tested in isolation and avoids capturing references to request state.

    Args:
        file_path: Absolute or relative path to the temporary PDF file.
    """
    try:
        rag_manager = await PostgresRAGManager.create(engine, VECTOR_TABLE_NAME, OLLAMA_HOST)
        await rag_manager.index_file(file_path)
    except Exception as exc:
        logger.error(f"Background indexing failed for {file_path}: {exc}", exc_info=True)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/")
async def status():
    """Root endpoint — confirms the agent is running."""
    return {"status": "Agent Active", "version": "1.0.0"}


@router.get("/health")
async def health_check(request: Request):
    """Comprehensive health check including Kafka consumer state."""
    kafka_svc = request.app.state.kafka_service
    return {
        "status": "healthy",
        "kafka_connected": kafka_svc.is_connected,
        "kafka_task_running": kafka_svc.is_running,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/rag")
async def rag_health_check(request: Request):
    """Health check specifically for the RAG service."""
    rag_service = request.app.state.rag_service
    if rag_service is None:
        return {"status": "unhealthy", "error": "RAG service not initialised"}
    return await rag_service.health_check()


@router.get("/history", response_model=List[ClinicalAlertResponse])
async def get_alert_history(
    request: Request,
    limit: int = 10,
    patient_id: Optional[str] = None,
):
    """Retrieve recent clinical alerts. If patient_id is omitted, returns all patients."""
    session_factory = request.app.state.session_factory
    history_svc = AlertHistory(session_factory)
    return await history_svc.get_alert_history(limit, patient_id)


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> UploadResponse:
    """
    Upload a PDF file for medical knowledge indexing.

    The file is saved to a temporary path then indexed asynchronously
    in a background task so the HTTP response returns immediately.
    """
    if not file.filename or not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    temp_id = str(uuid.uuid4())
    temp_path = f"temp_{temp_id}_{file.filename}"

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)  # type: ignore[arg-type]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}")

    background_tasks.add_task(_run_indexing, temp_path)

    return UploadResponse(
        message=f"File '{file.filename}' uploaded successfully.",
        status="Indexing started in background",
        job_id=temp_id,
    )
