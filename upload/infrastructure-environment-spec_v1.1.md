# Infrastructure & Environment Specification (v1)

**Target Hardware**: GTX 3070 Ti (8GB VRAM) or similar consumer GPU
**Constraint**: Models ≤ 7B parameters preferred for comfort. Long-context embedding models should fit in ~6-7GB VRAM when loaded.

## 1. Recommended Base Image & Python Version (Stabilized)

**Recommended (more stable than bleeding-edge)**:
- Base: `nvidia/cuda:12.4.1-devel-ubuntu22.04` or `ubuntu24.04` with CUDA 13.3
- Python: 3.4


## 2. Dockerfile Structure (Multi-stage Recommended)

**Stage 1: Model Downloader** (run once)
```dockerfile
FROM python:3.12-slim as model-downloader
# Install huggingface_hub + git-lfs
# Download only the models needed for v1:
# - BAAI/bge-m3 (or smaller alternative)
# - jinaai/jina-embeddings-v3 or v5 small variant suitable for long context
# - Optional: cross-encoder reranker (small)
```

**Stage 2: Runtime**
```dockerfile
FROM nvidia/cuda:13.3.0-devel-ubuntu26.04
# Install Python 3.12, minimal system deps
# Copy models from model-downloader stage
# Install runtime dependencies (transformers, neo4j, fastapi, etc.)
# Do NOT install heavy dev tools in final image
```

## 3. docker-compose.yml (v1 Services)

```yaml
services:
  neo4j:
    image: neo4j:5.20-community
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      NEO4J_AUTH: neo4j/P@ssw0rd
      NEO4J_PLUGINS: '["apoc"]'   # if needed
    volumes:
      - neo4j_data:/data

  redis:
    image: redis:7-alpine
    # Used for job queue (RQ or similar) and progress tracking

  backend:
    build: .
    ports:
      - "8000:8000"
    environment:
      - NEO4J_URI=bolt://neo4j:7687
      - NEO4J_USER=neo4j
      - NEO4J_PASSWORD=P@ssw0rd
      - REDIS_URL=redis://redis:6379/0
      - MODEL_PATH=/app/models
      - CUDA_VISIBLE_DEVICES=0
    depends_on:
      - neo4j
      - redis
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  api-worker:
    build: .
    command: python -m app.workers.worker   # RQ worker or similar
    environment:
      - REDIS_URL=redis://redis:6379/0
      - MODEL_PATH=/app/models
    depends_on:
      - redis
      - backend
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend
```

## 4. Model Recommendations for GTX 3070 Ti (v1)

**Primary Recommendations (fit comfortably)**:
- Embedding: `BAAI/bge-m3` (1024 dim, strong multilingual & long context performance)
- Alternative smaller: `jinaai/jina-embeddings-v3` or latest small long-context variant
- Reranker (optional in Slice 5): Small cross-encoder (e.g. `BAAI/bge-reranker-base` or Jina reranker small)

**Avoid in v1**:
- Llama-3.1-8B or larger for chunking/context (use only if researcher explicitly wants agentic features later)
- Very large long-context models that exceed ~6.5GB VRAM under load

## 5. Environment Variables (.env.example)

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=P@ssw0rd
REDIS_URL=redis://localhost:6379/0
MODEL_PATH=/app/models
LOG_LEVEL=INFO
EXPERIMENT_STORAGE_PATH=/app/experiments   # if storing metadata files
```

## 6. One-time Setup Commands (documented in README)

```bash
# 1. Build images
docker compose build

# 2. Download models (run once)
docker compose run --rm backend python scripts/download_models.py

# 3. Initialize Neo4j indexes & constraints
docker compose run --rm backend python scripts/init_neo4j.py

# 4. Start everything
docker compose up -d
```

This setup keeps the system reproducible and aligned with the GTX 3070 Ti constraint while avoiding overly bleeding-edge dependencies.