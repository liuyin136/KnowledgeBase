from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.middleware.otel import setup_otel, shutdown_otel
from app.routers import files, graph, jobs, knowledge, memory, search, vault
from app.services import file_store
from app.services.vault_db import init_vault_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(get_settings().otel_service_name)
    file_store.ensure_data_dirs()
    init_vault_db()
    yield
    shutdown_otel()


app = FastAPI(title="RAG Lab Baseline", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin] if settings.frontend_origin != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

setup_otel(app)

app.include_router(files.router)
app.include_router(jobs.router)
app.include_router(knowledge.router)
app.include_router(search.router)
app.include_router(vault.router)
app.include_router(memory.router)
app.include_router(graph.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
