"""
Routers package — re-exports all APIRouter instances.

Import pattern in main.py:
    from app.backend.routers import core, patients, chatbot
    app.include_router(core.router)
"""
from app.backend.routers import chatbot, core, patients

__all__ = ["core", "patients", "chatbot"]

