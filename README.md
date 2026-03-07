# 🏥 Sentinel Health Agent

An AI-powered, real-time clinical alert monitoring system. Consumes patient vitals from Apache Kafka, enriches alerts with **Retrieval-Augmented Generation (RAG)** using local LLMs via Ollama, onboards patients with full medical history, and provides nurses with a **LangGraph + MCP-powered chatbot** for clinical consultation.

> Built to showcase production-level GenAI engineering: LangGraph agents, MCP tool-calling, RAG pipelines, real-time streaming, and multi-page Streamlit dashboards.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        SENTINEL HEALTH AGENT v1.0                            │
│                                                                              │
│  ┌─────────────┐     ┌────────────────────────────────────────────────────┐ │
│  │ simulator.py│     │              FastAPI Backend                        │ │
│  │  (Producer) │────▶│  /  /health  /history  /upload  /health/rag        │ │
│  └─────────────┘     │  /patients  /patients/{id}/history                 │ │
│         │            │  /chat  /chat/{session_id}  /chat/sessions          │ │
│         ▼            └───────────────────┬────────────────────────────────┘ │
│  ┌─────────────┐                         │                                  │
│  │   Apache    │    ┌────────────────────▼───────────────────────────────┐  │
│  │    Kafka    │───▶│       KafkaConsumerService (background task)        │  │
│  │   (topic)   │    │    Polls CRITICAL / WARNING vitals alerts           │  │
│  └─────────────┘    └────────────────────┬───────────────────────────────┘  │
│                                          │                                  │
│                                          ▼                                  │
│                     ┌────────────────────────────────────────────────────┐  │
│                     │              ProcessAlerts Service                  │  │
│                     │                                                    │  │
│                     │  1. Fetch patient profile   (patients table)       │  │
│                     │  2. Fetch medical history   (medical_history)      │  │
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
│  │                   Streamlit Dashboard (Multi-page)                      │ │
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
simulator.py  →  Kafka (vitals_stream)  →  KafkaConsumerService
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
| **FastAPI App** | `app/backend/main.py` | Lifespan, router registration (≈90 lines) |
| **Database** | `app/backend/database.py` | Async engine, `async_sessionmaker`, env validation |
| **Kafka Consumer** | `app/backend/services/kafka_consumer.py` | `KafkaConsumerService` — polling loop, retry, graceful shutdown |
| **Alert Processor** | `app/backend/services/process_alerts.py` | Patient-aware alert enrichment pipeline |
| **RAG Service** | `app/backend/services/rag_service.py` | pgvector similarity search + Ollama LLM (`MedicalRAG`) |
| **Alert History** | `app/backend/services/history.py` | PostgreSQL alert retrieval |
| **LLM Prompts** | `app/backend/services/prompts.py` | Clinical prompt templates (basic + enriched) |
| **LangGraph Agent** | `app/backend/agent/chatbot_graph.py` | `ChatbotGraphBuilder` class — StateGraph + MemorySaver |
| **MCP Tools** | `app/backend/mcp_tools/patient_tools.py` | `PatientToolkit` class — `StructuredTool` wrappers |
| **Core Router** | `app/backend/routers/core.py` | `/` `/health` `/health/rag` `/history` `/upload` |
| **Patients Router** | `app/backend/routers/patients.py` | CRUD for Patient + MedicalHistory |
| **Chatbot Router** | `app/backend/routers/chatbot.py` | `POST /chat`, session management |
| **DB Models** | `app/backend/models.py` | SQLAlchemy 2.x ORM (Patient, MedicalHistory, ClinicalAlert) |
| **Schemas** | `app/backend/schemas.py` | Pydantic request/response validation |
| **Config** | `app/utils/config.py` | Environment variable loading with validation |
| **Retry** | `app/utils/retry.py` | Async retry decorator with exponential backoff + jitter |
| **PDF Ingestor** | `app/vector_db/ingest_pdf.py` | `PostgresRAGManager` — PDF → chunk → embed → pgvector |
| **Simulator** | `simulator.py` | Kafka vitals producer (round-robin, keyed by patient) |
| **DB Init** | `init_db.py` | Schema creation (pgvector extension + all tables) |

---

## 📁 Project Structure

```
sentinel-health-agent/
├── app/
│   ├── __init__.py                    # setup_logging() — shared named logger
│   ├── backend/
│   │   ├── main.py                    # FastAPI app, lifespan, router registration
│   │   ├── database.py                # Async engine + async_sessionmaker
│   │   ├── models.py                  # SQLAlchemy 2.x ORM models (3 tables)
│   │   ├── schemas.py                 # Pydantic request/response schemas
│   │   ├── constants.py               # Kafka + app-level constants
│   │   ├── agent/
│   │   │   └── chatbot_graph.py       # ChatbotGraphBuilder (LangGraph StateGraph)
│   │   ├── mcp_tools/
│   │   │   └── patient_tools.py       # PatientToolkit (MCP StructuredTools)
│   │   ├── routers/
│   │   │   ├── core.py                # /health /history /upload endpoints
│   │   │   ├── patients.py            # /patients CRUD endpoints
│   │   │   └── chatbot.py             # /chat endpoints + session management
│   │   ├── services/
│   │   │   ├── kafka_consumer.py      # KafkaConsumerService class
│   │   │   ├── process_alerts.py      # Alert enrichment pipeline
│   │   │   ├── rag_service.py         # MedicalRAG class
│   │   │   ├── history.py             # AlertHistory class
│   │   │   └── prompts.py             # ClinicalPrompts class
│   │   └── store/                     # Reserved for future caching utilities
│   ├── dashboard/
│   │   ├── home.py                    # Landing page (Streamlit entrypoint)
│   │   └── pages/
│   │       ├── 1_Live_Alerts.py       # Real-time alert feed (auto-refreshes)
│   │       ├── 2_Patient_Onboarding.py # Register patients + medical history
│   │       ├── 3_Alert_History.py     # Per-patient alert timeline + charts
│   │       └── 4_Nurse_Chatbot.py     # LangGraph chatbot UI
│   ├── utils/
│   │   ├── config.py                  # Env config with required/optional validation
│   │   └── retry.py                   # Async retry with exponential backoff + jitter
│   └── vector_db/
│       ├── ingest_pdf.py              # PostgresRAGManager — PDF → pgvector pipeline
│       └── data/
│           └── tachycardia_1.pdf      # Sample clinical knowledge PDF
├── simulator.py                       # Kafka vitals producer (round-robin)
├── init_db.py                         # DB schema setup
├── docker-compose.yml                 # PostgreSQL (pgvector) + Kafka + Kafka UI
├── pyproject.toml
├── requirements.txt
└── .env.example
```

---

## 🗄️ Database Schema

```sql
-- Patient demographics (PII-sensitive table)
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

-- Medical history (separate table — isolated from demographics for data safety)
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

-- Clinical alerts generated from Kafka vitals stream
CREATE TABLE clinical_alerts (
    id          SERIAL PRIMARY KEY,
    patient_id  VARCHAR REFERENCES patients(id),
    heart_rate  INTEGER,
    status      VARCHAR CHECK (status IN ('NORMAL', 'WARNING', 'CRITICAL')),
    ai_advice   TEXT,
    timestamp   TIMESTAMPTZ DEFAULT NOW()
);

-- pgvector embeddings table (medical knowledge base)
-- Created automatically by PostgresRAGManager on first run
```

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- [Ollama](https://ollama.com/) running on your machine or LAN

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env — set OLLAMA_HOST, POSTGRES_* credentials, table names
```

### 2. Start Infrastructure

```bash
docker-compose up -d
# Starts: PostgreSQL (with pgvector), Kafka (KRaft mode), Kafka UI
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

Upload via the dashboard, or directly via API:

```bash
curl -X POST http://localhost:8000/upload -F "file=@your_guidelines.pdf"
```

> A sample `tachycardia_1.pdf` is already included in `app/vector_db/data/`.

### 8. Start the Simulator

Open `simulator.py` and add your registered patient IDs to `PATIENT_IDS`:

```python
PATIENT_IDS = [
    "PAT-3F2A1B4C",   # copy auto-generated IDs from the Patient Onboarding page
    "PAT-A1B2C3D4",
]
```

Then run:

```bash
python simulator.py
```

The simulator **round-robins through all patients** every cycle — every patient gets one reading per interval, so the Live Alerts dashboard always shows data for everyone.

```
🚀 Simulator started  |  topic: vitals_stream  |  patients: 2  |  interval: 2.0s / cycle
   Pool  : ['PAT-3F2A1B4C', 'PAT-A1B2C3D4']
   Rates : CRITICAL=10%  WARNING=15%  NORMAL=75%

🟢 [cycle 0001 | #00001]  Patient: PAT-3F2A1B4C   |  HR:  72 BPM  |  SpO2: 97%  |  NORMAL
🟡 [cycle 0001 | #00002]  Patient: PAT-A1B2C3D4   |  HR: 108 BPM  |  SpO2: 96%  |  WARNING
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
| `GET` | `/health` | System health (Kafka connected + task running) |
| `GET` | `/health/rag` | RAG health (embeddings, vector store, LLM) |
| `GET` | `/history` | Alert history — all patients if no `patient_id` param |
| `POST` | `/upload` | Upload PDF for RAG knowledge base indexing |
| `POST` | `/patients` | Register new patient |
| `GET` | `/patients` | List all patients |
| `GET` | `/patients/{id}` | Get patient by ID |
| `PUT` | `/patients/{id}` | Update patient demographics |
| `POST` | `/patients/{id}/history` | Create or update medical history (upsert) |
| `GET` | `/patients/{id}/history` | Get patient medical history |
| `POST` | `/chat` | Send nurse message to LangGraph agent |
| `DELETE` | `/chat/{session_id}` | Clear conversation history (idempotent) |
| `GET` | `/chat/sessions` | List active chat session IDs |

---

## 🤖 LangGraph Agent — How It Works

The Nurse Chatbot uses a **ReAct-style LangGraph `StateGraph` built by `ChatbotGraphBuilder`**:

```
AgentState:
  messages    → Full conversation history (add_messages reducer — appends, never replaces)
  patient_id  → Which patient the nurse is consulting about
  tools_used  → MCP tools called this turn (returned to UI for transparency)

Graph:
  START → llm_node → (conditional) → tool_executor → llm_node → ... → END

Checkpointer: MemorySaver (keyed by session_id)
              Preserves full conversation history across multiple HTTP requests
```

```python
# Build and compile
toolkit  = PatientToolkit(session, rag_service)
compiled = ChatbotGraphBuilder(toolkit.get_tools()).build()
```

**Available MCP tools:**

| Tool | Description |
|------|-------------|
| `get_patient_profile` | Demographics — name, DOB, gender, contact info |
| `get_medical_history` | Allergies, medications, chronic conditions, notes |
| `get_recent_alerts` | Latest N vital sign alerts with AI advice |
| `search_medical_knowledge` | RAG similarity search over clinical PDFs |

---

## 🎛️ Simulator Configuration

| Env Variable | Default | Description |
|---|---|---|
| `SEND_INTERVAL_SECONDS` | `2` | Seconds between full patient cycles |
| `CRITICAL_CHANCE` | `0.10` | Probability of CRITICAL reading (HR 121–160 BPM) |
| `WARNING_CHANCE` | `0.15` | Probability of WARNING reading (HR 101–120 BPM) |

**Key design decisions:**
- **Round-robin per cycle** — every patient in `PATIENT_IDS` receives one reading per cycle. The Live Alerts dashboard always shows fresh data for all patients.
- **Kafka key = `patient_id`** — routes all readings for the same patient to the same partition, preserving per-patient message ordering.
- **Monotonic timing** — `time.monotonic()` keeps the cycle interval accurate even when multiple patients are in the pool.
- **Startup validation** — probability values are validated at import time; the process exits fast with a clear error if misconfigured.

---

## 🐳 Docker Services

```yaml
services:
  db:         # pgvector/pgvector:pg17 — PostgreSQL with pgvector extension
  kafka:      # apache/kafka:3.7.1 — KRaft mode (no Zookeeper required)
  kafka-ui:   # provectuslabs/kafka-ui — browse topics and messages in browser
```

---

## 🔧 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_HOST` | ✅ | PostgreSQL host |
| `POSTGRES_USER_NAME` | ✅ | DB username |
| `POSTGRES_PASSWORD` | ✅ | DB password |
| `POSTGRES_DB` | ✅ | Database name |
| `POSTGRES_CLINICAL_ALERTS_TABLE` | ✅ | Alerts table name |
| `POSTGRES_PATIENTS_TABLE` | ❌ | Patients table (default: `patients`) |
| `POSTGRES_MEDICAL_HISTORY_TABLE` | ❌ | History table (default: `medical_history`) |
| `VECTOR_TABLE_NAME` | ✅ | pgvector embeddings table name |
| `KAFKA_BOOTSTRAP_SERVERS` | ✅ | Kafka broker address (e.g. `localhost:9092`) |
| `KAFKA_CONSUMER_TOPIC` | ✅ | Topic to consume/produce (e.g. `vitals_stream`) |
| `OLLAMA_HOST` | ✅ | Ollama server URL (e.g. `http://192.168.x.x:11434`) |
| `MEDICAL_EMBEDDING_MODEL` | ✅ | Embedding model (e.g. `nomic-embed-text`) |
| `LLM_MODEL` | ✅ | LLM for alerts + chatbot (e.g. `llama3.2`) |
| `NO_PROXY` | ❌ | Bypass proxy for Ollama host |
| `LOG_LEVEL` | ❌ | Logging level (default: `INFO`) |

---

## 💡 Suggested Additional Features

| Feature | Why It's Interesting |
|---------|----------------------|
| **SBAR Report Generation** | LangGraph multi-step autonomous reasoning per CRITICAL alert |
| **Multi-vital analysis** | Add SpO2/BP to Kafka schema; detect dangerous vital combinations |
| **Human-in-the-loop** | `interrupt()` node before saving AI advice — nurse approves/edits |
| **RAG evaluation page** | Show retrieved chunks + similarity scores per alert |
| **Real MCP Server** | Wrap `patient_tools.py` with `FastMCP` (official MCP SDK) over SSE transport |

---

## 📄 License

MIT License
