from fastapi import FastAPI

app = FastAPI(title="RAG Lab Baseline")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
