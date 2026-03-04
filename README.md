# 🏥 Sentinel Health Agent

An AI-powered, real-time clinical alert monitoring system that consumes patient vitals from Apache Kafka, enriches alerts with Retrieval-Augmented Generation (RAG) using local LLMs via Ollama, and persists structured clinical recommendations to PostgreSQL.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SENTINEL HEALTH AGENT                        │
│                                                                     │
│  ┌──────────────┐    ┌─────────────────────────────────────────┐   │
│  │  simulator.py│    │           FastAPI Backend                │   │
│  │  (Producer)  │───▶│  /health  /history  /upload  /health/rag│   │
│  └──────────────┘    └────────────────┬────────────────────────┘   │
│         │                             │                             │
│         ▼                             ▼                             │
│  ┌──────────────┐    ┌─────────────────────────────────────────┐   │
│  │    Apache    │    │           Kafka Consumer Loop            │   │
│  │    Kafka     │───▶│   blocking_kafka_loop()                  │   │
│  │   (Topic)    │    │   Polls CRITICAL / WARNING alerts        │   │
│  └──────────────┘    └────────────────┬────────────────────────┘   │
│                                       │                             │
│                                       ▼                             │
│                      ┌────────────────────────────────────────┐    │
│                      │         ProcessAlerts Service           │    │
│                      │                                        │    │
│                      │  1. Fetch patient profile (UserStore)  │    │
│                      │  2. Query RAG for medical context      │    │
│                      │  3. Send enriched prompt → Ollama LLM  │    │
│                      │  4. Parse structured clinical response  │    │
│                      │  5. Persist alert to PostgreSQL         │    │
│                      └────────────────┬───────────────────────┘    │
│                                       │                             │
│              ┌────────────────────────┼──────────────────┐         │
│              ▼                        ▼                  ▼         │
│  ┌─────────────────┐  ┌───────────────────────┐  ┌──────────────┐ │
│  │   PostgreSQL    │  │     MedicalRAG         │  │    Ollama    │ │
│  │                 │  │  (pgvector similarity) │  │  (Local LLM) │ │
│  │ • alerts table  │  │  • PDF ingestion       │  │  • llama3.2  │ │
│  │ • vector table  │  │  • chunk embeddings    │  │  • nomic-    │ │
│  │                 │  │  • similarity search   │  │    embed-text│ │
│  └─────────────────┘  └───────────────────────┘  └──────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                  Streamlit Dashboard                          │  │
│  │            Real-time alert history viewer                     │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Data Flow

```
simulator.py
    │
    │  Produces JSON vitals every N seconds
    │  { patient_id, heart_rate, status: CRITICAL/WARNING/NORMAL }
    ▼
Apache Kafka (topic: health-alerts)
    │
    │  KafkaConsumer polls in background asyncio task
    ▼
ProcessAlerts.process_critical_alert(data, heart_rate)
    │
    ├──▶ UserStore → fetch patient demographics/history
    │
    ├──▶ MedicalRAG → pgvector similarity search
    │         └──▶ Returns relevant medical knowledge chunks
    │
    ├──▶ Ollama LLM → enriched clinical prompt
    │         └──▶ Returns structured JSON recommendation
    │
    └──▶ PostgreSQL → persist ClinicalAlert record
              └──▶ Available via GET /history
```

---

## 🧩 Component Overview

| Component | File | Responsibility |
|-----------|------|----------------|
| **FastAPI App** | `app/backend/main.py` | HTTP server, lifespan, Kafka task |
| **Alert Processor** | `app/backend/services/process_alerts.py` | Core alert enrichment pipeline |
| **RAG Service** | `app/backend/services/rag_service.py` | Vector similarity search |
| **Alert History** | `app/backend/services/history.py` | PostgreSQL alert retrieval |
| **PDF Ingestor** | `app/vector_db/ingest_pdf.py` | Chunk, embed, store PDFs |
| **LLM Prompts** | `app/backend/services/prompts.py` | Clinical prompt templates |
| **User Store** | `app/backend/store/user_store.py` | Patient profile management |
| **Medical KB** | `app/backend/store/medical_knowledge.py` | Static knowledge base |
| **DB Models** | `app/backend/models.py` | SQLAlchemy ORM models |
| **Schemas** | `app/backend/schemas.py` | Pydantic request/response schemas |
| **Config** | `app/utils/config.py` | Environment variable loading |
| **Retry** | `app/utils/retry.py` | Resilient async retry decorator |
| **Simulator** | `simulator.py` | Kafka producer for testing |
| **DB Init** | `init_db.py` | Schema creation + seed data |
| **Dashboard** | `app/dashboard/home.py` | Streamlit UI |

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Ollama installed locally or via Docker

### 1. Clone & Configure

```bash
git clone <repo-url>
cd sentinel-health-agent
cp .env.example .env   # Edit with your values
```

### 2. Environment Variables

```env
# Database Credentials
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER_NAME=admin
POSTGRES_PASSWORD=password123
POSTGRES_DB=health_agent
POSTGRES_CLINICAL_ALERTS_TABLE=clinical_alerts
VECTOR_TABLE_NAME=medical_knowledge

# Kafka Settings
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_CONSUMER_TOPIC=vitals_stream

# Ollama Settings
OLLAMA_HOST=http://192.168.1.2:11434
NO_PROXY=localhost,127.0.0.1,192.168.1.2
MEDICAL_EMBEDDING_MODEL=nomic-embed-text
LLM_MODEL=llama3
```

### 3. Start Infrastructure

```bash
docker-compose up -d
```

### 4. Pull Required Ollama Models

```bash
ollama pull llama3.2
ollama pull nomic-embed-text
```

### 5. Initialize Database

```bash
python init_db.py
```

### 6. Install Dependencies

```bash
pip install -e .
```

### 7. Run the Agent

```bash
uvicorn app.backend.main:app --host 0.0.0.0 --port 8000
```

### 8. Run the Simulator (separate terminal)

```bash
python simulator.py
```

### 9. Launch Dashboard

```bash
streamlit run app/dashboard/home.py
```

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Agent status |
| `GET` | `/health` | Comprehensive health check |
| `GET` | `/health/rag` | RAG service health |
| `GET` | `/history` | Alert history (paginated) |
| `POST` | `/upload` | Upload PDF for indexing |

### Example: Get Alert History

```bash
curl "http://localhost:8000/history?limit=10&patient_id=PATIENT_001"
```

### Example: Upload Medical PDF

```bash
curl -X POST "http://localhost:8000/upload" \
  -F "file=@tachycardia_guide.pdf"
```

---

## 🐳 Docker Compose Services

```yaml
services:
  - postgres     # PostgreSQL 15 + pgvector extension
  - kafka        # Apache Kafka (KRaft mode)
  - ollama       # Local LLM server
  - backend      # FastAPI application
  - dashboard    # Streamlit UI
```

---

## 📊 Database Schema

```sql
-- Clinical Alerts
CREATE TABLE clinical_alerts (
    id          UUID PRIMARY KEY,
    patient_id  VARCHAR,
    heart_rate  INTEGER,
    status      VARCHAR,        -- CRITICAL / WARNING
    analysis    TEXT,           -- LLM clinical analysis
    action      TEXT,           -- Recommended action
    severity    VARCHAR,
    timestamp   TIMESTAMPTZ DEFAULT NOW()
);

-- Vector Embeddings (pgvector)
CREATE TABLE medical_embeddings (
    id        UUID PRIMARY KEY,
    content   TEXT,
    embedding VECTOR(768),      -- nomic-embed-text dimensions
    metadata  JSONB
);
```

---

## 🔧 Development

### Project Structure

```
sentinel-health-agent/
├── app/
│   ├── backend/
│   │   ├── main.py              # FastAPI + Kafka consumer
│   │   ├── models.py            # SQLAlchemy models
│   │   ├── schemas.py           # Pydantic schemas
│   │   ├── constants.py         # Kafka constants
│   │   └── services/
│   │       ├── process_alerts.py # Alert pipeline
│   │       ├── rag_service.py    # Vector search
│   │       ├── history.py        # Alert history
│   │       └── prompts.py        # LLM prompts
│   ├── store/
│   │   ├── user_store.py        # Patient profiles
│   │   └── medical_knowledge.py # Static KB
│   ├── vector_db/
│   │   └── ingest_pdf.py        # PDF → pgvector pipeline
│   ├── dashboard/
│   │   └── home.py              # Streamlit UI
│   └── utils/
│       ├── config.py            # Env config
│       └── retry.py             # Retry decorator
├── simulator.py                 # Kafka producer
├── init_db.py                   # DB setup
├── docker-compose.yml
└── requirements.txt
```

### Running Tests

```bash
pytest tests/ -v
```

---

## ⚠️ Known Issues & Roadmap

- [ ] Authentication/Authorization (JWT)
- [ ] Multi-patient concurrent processing
- [ ] Alert deduplication logic
- [ ] Metrics endpoint (Prometheus)
- [ ] Alert webhook notifications
- [ ] Frontend beyond Streamlit

---

## 📄 License

MIT License — see `LICENSE` for details.
