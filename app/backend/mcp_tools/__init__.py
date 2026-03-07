"""
MCP Tools package.

Exposes PatientToolkit — the class that provides LangChain tools for
the nurse chatbot agent.  Build tools with:

    from app.backend.mcp_tools.patient_tools import PatientToolkit
    tools = PatientToolkit(session, rag_service).get_tools()
"""
from app.backend.mcp_tools.patient_tools import PatientToolkit

__all__ = ["PatientToolkit"]

