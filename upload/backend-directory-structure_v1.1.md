# Backend Project Directory Structure (v1)

**Purpose**: Clean, modular, testable structure following the approved architecture (PipelineOrchestrator + strict module boundaries).

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI application factory + lifespan events
│   │
│   ├── core/
│   │   ├── config.py                    # Pydantic Settings (env vars, model paths, Neo4j URI)
│   │   ├── logging.py                   # Structured logging setup (structlog or logging + JSON)
│   │   ├── exceptions.py                # Custom exception hierarchy + error codes
│   │   └── constants.py                 # Enums (ChunkMethod, EmbeddingApproach, etc.)
│   │
│   ├── api/
│   │   ├── v1/
│   │   │   ├── router.py                # Main APIRouter aggregation
│   │   │   ├── experiments.py           # /experiments endpoints
│   │   │   ├── documents.py             # /documents endpoints
│   │   │   ├── ingest.py                # /ingest endpoints (unified or split)
│   │   │   ├── search.py                # /search endpoints
│   │   │   └── memory.py                # /memories + /memory-carts
│   │   └── dependencies.py              # Common dependencies (get_db, get_current_experiment, etc.)
│   │
│   ├── schemas/                         # Pydantic v2 models (request + response)
│   │   ├── experiment.py
│   │   ├── document.py
│   │   ├── ingest.py
│   │   ├── search.py
│   │   ├── memory.py
│   │   └── common.py                    # Pagination, ErrorResponse, etc.
│   │
│   ├── services/                        # Business logic (thin orchestrator layer)
│   │   ├── orchestrator.py              # PipelineOrchestrator – coordinates everything
│   │   ├── chunking.py                  # ChunkingModule
│   │   ├── embedding.py                 # EmbeddingModule (standard paths only)
│   │   ├── retrieval.py                 # RetrievalModule (Hybrid Search)
│   │   └── metadata.py                  # MetadataService – creates ChunkMetadata & ExperimentRun
│   │
│   ├── models/                          # Data transfer objects / Neo4j node representations
│   │   ├── neo4j_models.py              # Pydantic or dataclasses for Knowledge, KnowledgeChunk, etc.
│   │   └── enums.py
│   │
│   ├── db/
│   │   ├── neo4j_client.py              # Thin wrapper around neo4j driver + session management
│   │   └── vector_index.py              # Helper to create/ensure vector indexes
│   │
│   ├── workers/                         # Background / long-running task handling
│   │   ├── tasks.py                     # Ingest task, Search task (can use RQ, Celery, or FastAPI BackgroundTasks + Redis)
│   │   └── progress.py                  # SSE / progress tracking helpers
│   │
│   └── utils/
│       ├── tokenization.py
│       └── timing.py
│
├── tests/
│   ├── unit/
│   │   ├── test_chunking.py
│   │   ├── test_embedding.py
│   │   └── test_retrieval.py
│   ├── integration/
│   │   └── test_ingest_flow.py
│   └── contract/
│       └── test_api_contract.py         # Contract tests against OpenAPI spec
│
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── scripts/
│   ├── download_models.py               # One-time model download script
│   └── init_neo4j.py                    # Index creation + constraint scripts
│
├── pyproject.toml
├── requirements.txt
├── .env.example
└── README.md
```

**Key Principles Applied**
- Thin `services/orchestrator.py` owns coordination and metadata.
- `api/` is only for HTTP concerns.
- `schemas/` for all Pydantic contracts (single source of truth for API).
- Clear separation between `ChunkingModule`, `EmbeddingModule`, and `RetrievalModule`.
- `workers/` for long-running ingest/search to keep API responsive.

This structure supports the 6-slice incremental implementation and makes future addition of Late/Agentic paths easy (new files under `services/` behind feature flags).