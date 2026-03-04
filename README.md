# 🏥 Sentinel Health Agent
An AI-powered, real-time clinical alert monitoring system. Consumes patient vitals from Apache Kafka, enriches alerts with **Retrieval-Augmented Generation (RAG)** using local LLMs via Ollama, onboards patients with full medical history, and provides nurses with a **LangGraph + MCP-powered chatbot** for clinical consultation.
> Built to showcase production-level GenAI engineering: LangGraph agents, MCP tool-calling, RAG pipelines, real-time streaming, and multi-page dashboards.
---
## 🏗️ Architecture
```
┌──────────────────────────────────────────────────────────────────────────────┐
#                          SENTINEL HEALTH AGENT v1.0                          #
│                                                                              │
│  ┌─────────────┐     ┌────────────────────────────────────────────────────┐ │
│  │ simulator.py│     │              FastAPI Backend                        │ │
│  │  (Producer) │────▶│  /  /health  /history  /upload  /health/rag        │ │
│  └─────────────┘     │  /patients  /patients/{id}/history                 │ │
│         │            │  /chat  /chat/{session_id}                          │ │
│         ▼            └───────────────────┬────────────────────────────────┘ │
│  ┌─────────────┐                         │                                  │
│  │   Apache    │    ┌────────────────────▼───────────────────────────────┐  │
│  │    Kafka    │───▶│            Kafka Consumer Loop                      │  │
│  │   (topic)   │    │    Polls CRITICAL / WARNING vitals alerts           │  │
│  └─────────────┘    └────────────────────┬───────────────────────────────┘  │
│                                          │                                  │
│                                          ▼                                  │
│                     ┌────────────────────────────────────────────────────┐  │
│                     │            ProcessAlerts Service                    │  │
│                     │                                                    │  │
│                     │  1. Fetch Patient profile (patients table)         │  │
│                     │  2. Fetch Medical history (medical_history table)  │  │
│                     │  3. RAG search → pgvector similarity               │  │
│                     │  4. Enriched prompt → Ollama LLM                   │  │
│                     │  5. Save ClinicalAlert to DB                       │  │
│                     └──────────────┬─────────────────────────────────────┘  │
│                                    │                                        │
│         ┌──────────────────────────┼──────────────────────┐                 │
│         ▼                          ▼                      ▼                 │
│  ┌─────────────┐    ┌──────────────────────┐   ┌──────────────────────┐    │
│  │  PostgreSQL │    │    MedicalRAG         │   │  Ollama (WiFi/LAN)   │    │
│  │             │    │  (langchain-postgres) │   │                      │    │
│  │ • patients  │    │  • PDF ingestion      │   │  • llama3.2 (LLM)    │    │
│  │ • med_hist  │    │  • nomic embeddings   │   │  • nomic-embed-text  │    │
│  │ • alerts    │    │  • pgvector search    │   │    (embeddings)      │    │
│  │ • vectors   │    └──────────────────────┘   └──────────────────────┘    │
│  └─────────────┘                                                            │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    LangGraph Nurse Chatbot Agent                        │ │
│  │                                                                        │ │
│  │   START → llm_node (ChatOllama + tools) ─┬─▶ tool_executor ──┐        │ │
│  │                                          │   (ToolNode/MCP)  │        │ │
│  │                                          └───────────────────┘        │ │
│  │                                          └─▶ END                      │ │
│  │                                                                        │ │
│  │   MCP Tools:  get_patient_profile  |  get_medical_history              │ │
│  │               get_recent_alerts    |  search_medical_knowledge         │ │
│  │                                                                        │ │
│  │   Memory: MemorySaver (per session_id thread)                          │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                     Streamlit Dashboard (Multi-page)                    │ │
│  │                                                                        │ │
│  │  🏠 Home  |  🚨 Live Alerts  |  📋 Patient Onboarding                  │ │
│  │  📊 Alert History  |  💬 Nurse Chatbot                                 │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```
---
## 🔄 Data Flow
### Alert Pipeline
```
simulator.py  →  Kafka (vitals_stream)  →  Kafka Consumer
    →  ProcessAlerts:
         ├── DB: Fetch patient demographics
         ├── DB: Fetch medical history (allergies, meds, conditions)
         ├── pgvector: Similarity search for clinical guidelines
         ├── Ollama LLM: Enriched prompt with patient context
         └── DB: Save ClinicalAlert with AI advice
    →  Available via GET /history  →  Streamlit Live Alerts page
```
### Nurse Chatbot Flow
```
Nurse types message  →  POST /chat  →  LangGraph Agent:
    START
      └─▶ llm_node (ChatOllama + 4 MCP tools)
               │
               ├─▶ [tool calls?] YES → tool_executor (ToolNode)
               │       ├── get_patient_profile(patient_id)
               │       ├── get_medical_history(patient_id)
               │       ├── get_recent_alerts(patient_id)
               │       └── search_medical_knowledge(query)
               │       └─▶ llm_node (loop until no more tool calls)
               │
               └─▶ [tool calls?] NO → END
    →  Response + tools_used  →  Streamlit chat UI
```
---
## 🧩 Component Overview
| Component | File | Responsibility |
|-----------|------|----------------|
| **FastAPI App** | `app/backend/main.py` | HTTP server, lifespan, Kafka task, router registration |
| **Alert Processor** | `app/backend/services/process_alerts.py` | Patient-aware alert enrichment pipeline |
| **RAG Service** | `app/backend/services/rag_service.py` | pgvector similarity search + Ollama LLM |
| **LangGraph Agent** | `app/backend/agent/chatbot_graph.py` | StateGraph with MemorySaver, tool-calling loop |
| **MCP Tools** | `app/backend/mcp_tools/patient_tools.py` | `@tool` decorated functions for the LangGraph agent |
| **Patients Router** | `app/backend/routers/patients.py` | CRUD for Patient + MedicalHistory tables |
| **Chatbot Router** | `app/backend/routers/chatbot.py` | POST /chat + session management |
| **Alert History** | `app/backend/services/history.py` | PostgreSQL alert retrieval |
| **PDF Ingestor** | `app/vector_db/ingest_pdf.py` | Chunk, embed, store PDFs into pgvector |
| **LLM Prompts** | `app/backend/services/prompts.py` | Clinical prompt templates (basic + enriched) |
| **DB Models** | `app/backend/models.py` | Patient, MedicalHistory, ClinicalAlert ORM models |
| **Schemas** | `app/backend/schemas.py` | Pydantic request/response validation |
| **Config** | `app/utils/config.py` | Environment variable loading |
| **Retry** | `app/utils/retry.py` | Async retry decorator for WiFi-hosted Ollama |
| **Simulator** | `simulator.py` | Kafka producer for testing |
| **DB Init** | `init_db.py` | Schema creation (pgvector + all tables) |
---
## 📁 Project Structure
```
sentinel-health-agent/
├── app/
│   ├── backend/
│   │   ├── main.py                    # FastAPI + Kafka consumer
│   │   ├── models.py                  # SQLAlchemy ORM models (3 tables)
│   │   ├── schemas.py                 # Pydantic schemas
│   │   ├── constants.py               # Kafka constants
│   │   ├── agent/
│   │   │   └── chatbot_graph.py       # LangGraph StateGraph (nurse chatbot)
│   │   ├── mcp_tools/
│   │   │   └── patient_tools.py       # MCP-style @tool functions
│   │   ├── routers/
│   │   │   ├── patients.py            # /patients CRUD endpoints
│   │   │   └── chatbot.py             # /chat endpoints
│   │   ├── services/
│   │   │   ├── process_alerts.py      # Alert enrichment pipeline
│   │   │   ├── rag_service.py         # RAG + LLM service
│   │   │   ├── history.py             # Alert history queries
│   │   │   └── prompts.py             # Prompt templates
│   │   └── store/
│   │       ├── user_store.py
│   │       └── medical_knowledge.py
│   ├── dashboard/
│   │   ├── home.py                    # Landing page (Streamlit entrypoint)
│   │   └── pages/
│   │       ├── 1_Live_Alerts.py       # Real-time alert feed
│   │       ├── 2_Patient_Onboarding.py # Register patients + medical history
│   │       ├── 3_Alert_History.py     # Per-patient alert timeline + charts
│   │       └── 4_Nurse_Chatbot.py     # LangGraph chatbot UI
│   ├── utils/
│   │   ├── config.py                  # Env config
│   │   └── retry.py                   # Retry decorator
│   └── vector_db/
│       └── ingest_pdf.py              # PDF → pgvector pipeline
├── simulator.py                       # Kafka producer
├── init_db.py                         # DB setup
├── docker-compose.yml
├── requirements.txt
└── .env.example
```
---
## 🗄️ Database Schema
```sql
-- Patient demographics (PII table)
CREATE TABLE patients (
    id              VARCHAR PRIMARY KEY,        -- auto-generated e.g. "PAT-3F2A1B4C"
    full_name       VARCHAR(200) NOT NULL,
    date_of_birth   DATE,
    gender          VARCHAR(20),
    contact_phone   VARCHAR(30),
    contact_email   VARCHAR(200),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
-- Medical history (separate table for data safety)
CREATE TABLE medical_history (
    id                  SERIAL PRIMARY KEY,
    patient_id          VARCHAR REFERENCES patients(id) UNIQUE,
    allergies           TEXT,
    current_medications TEXT,
    chronic_conditions  TEXT,
    past_surgeries      TEXT,
    family_history      TEXT,
    notes               TEXT,
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
-- Clinical alerts from Kafka stream
CREATE TABLE clinical_alerts (
    id          SERIAL PRIMARY KEY,
    patient_id  VARCHAR REFERENCES patients(id),
    heart_rate  INTEGER,
    status      VARCHAR CHECK (status IN ('NORMAL', 'WARNING', 'CRITICAL')),
    ai_advice   TEXT,
    timestamp   TIMESTAMPTZ DEFAULT NOW()
);
-- pgvector embeddings (medical knowledge base)
-- Created automatically by langchain-postgres PGVectorStore
```
---
## 🚀 Quick Start
### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Ollama running on your machine (or LAN)
### 1. Configure Environment
```bash
cp .env.example .env
# Edit .env with your values — especially OLLAMA_HOST and POSTGRES credentials
```
### 2. Start Infrastructure
```bash
docker-compose up -d
# Starts: PostgreSQL (with pgvector), Kafka (KRaft), Kafka UI
```
### 3. Pull Ollama Models
```bash
ollama pull llama3.2
ollama pull nomic-embed-text
```
### 4. Install Python Dependencies
```bash
pip install -e .
# or: pip install -r requirements.txt
```
### 5. Initialize Database
```bash
python init_db.py
# Creates: patients, medical_history, clinical_alerts tables + pgvector extension
```
### 6. Start the Backend
```bash
uvicorn app.backend.main:app --host 0.0.0.0 --port 8000
```
### 7. (Optional) Ingest Medical PDFs
```bash
# Via the /upload API endpoint or the dashboard Upload section
curl -X POST http://localhost:8000/upload -F "file=@your_guidelines.pdf"
```
### 8. Start the Simulator

Open `simulator.py` and add your registered patient IDs to the `PATIENT_IDS` list at the top:

```python
PATIENT_IDS = [
    "PAT-3F2A1B4C",   # copy auto-generated IDs from the Patient Onboarding page
    "PAT-A1B2C3D4",
]
```

Then run:

```bash
python simulator.py
# Randomly cycles through all patients in PATIENT_IDS, sends a reading every 2 seconds
```
### 9. Launch the Dashboard
```bash
streamlit run app/dashboard/home.py
# Opens on http://localhost:8501
```
---
## 📡 API Reference
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Agent status |
| `GET` | `/health` | System health check |
| `GET` | `/health/rag` | RAG service health |
| `GET` | `/history` | Alert history (filter by patient_id) |
| `POST` | `/upload` | Upload PDF for RAG indexing |
| `POST` | `/patients` | Register new patient |
| `GET` | `/patients` | List all patients |
| `GET` | `/patients/{id}` | Get patient by ID |
| `PUT` | `/patients/{id}` | Update patient info |
| `POST` | `/patients/{id}/history` | Upsert medical history |
| `GET` | `/patients/{id}/history` | Get medical history |
| `POST` | `/chat` | Nurse chatbot message |
| `DELETE` | `/chat/{session_id}` | Clear chat session |
| `GET` | `/chat/sessions` | List active chat sessions |
---
## 🤖 LangGraph Agent — How It Works
The Nurse Chatbot uses a **ReAct-style LangGraph `StateGraph`**:
```
AgentState:
  messages    → Full conversation history (add_messages reducer)
  patient_id  → Which patient the nurse is consulting about
  tools_used  → List of MCP tools called this turn (for UI transparency)
Graph:
  START → llm_node → (conditional) → tool_executor → llm_node → ... → END
Checkpointer: MemorySaver (keyed by session_id)
              Preserves conversation across multiple HTTP requests
```
**MCP Tool Pattern** — each tool is a `@tool`-decorated async function with a typed signature and docstring. LangChain automatically converts these to JSON schema for the LLM. The LLM decides autonomously which tools to call based on the nurse's question.
---
## 🐳 Docker Services
```yaml
services:
  db:         # pgvector/pgvector:pg17 — PostgreSQL with vector extension
  kafka:      # apache/kafka:3.7.1 — KRaft mode, no Zookeeper
  kafka-ui:   # provectuslabs/kafka-ui — browse topics and messages
```
---
## 🔧 Environment Variables
| Variable | Description | Required |
|----------|-------------|----------|
| `POSTGRES_HOST` | PostgreSQL host | ✅ |
| `POSTGRES_USER_NAME` | DB username | ✅ |
| `POSTGRES_PASSWORD` | DB password | ✅ |
| `POSTGRES_DB` | Database name | ✅ |
| `POSTGRES_CLINICAL_ALERTS_TABLE` | Alerts table name | ✅ |
| `POSTGRES_PATIENTS_TABLE` | Patients table (default: `patients`) | ❌ |
| `POSTGRES_MEDICAL_HISTORY_TABLE` | History table (default: `medical_history`) | ❌ |
| `VECTOR_TABLE_NAME` | pgvector table name | ✅ |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker address | ✅ |
| `KAFKA_CONSUMER_TOPIC` | Topic to consume | ✅ |
| `OLLAMA_HOST` | Ollama server URL (e.g. `http://192.168.x.x:11434`) | ✅ |
| `MEDICAL_EMBEDDING_MODEL` | Embedding model (e.g. `nomic-embed-text`) | ✅ |
| `LLM_MODEL` | LLM for alerts + chatbot (e.g. `llama3.2`) | ✅ |
| `NO_PROXY` | Bypass proxy for Ollama host | ❌ |
| `LOG_LEVEL` | Logging level (default: `INFO`) | ❌ |
---
## 💡 Suggested Additional Features
| Feature | Why It Impresses Interviewers |
|---------|-------------------------------|
| **SBAR Report Generation** | LangGraph multi-step autonomous reasoning on each CRITICAL alert |
| **Multi-vital analysis** | Add SpO2/BP to Kafka schema; detect dangerous vital combinations |
| **Human-in-the-loop** | `interrupt()` node before saving AI advice — nurse approves/edits |
| **RAG evaluation page** | Show retrieved chunks + similarity scores per alert (demonstrates RAG depth) |
| **Real MCP Server** | Wrap `patient_tools.py` with `FastMCP` (official MCP SDK) over SSE transport |
---
## 📄 License
MIT License
