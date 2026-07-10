# Run: docker compose exec api-worker python /app/scripts/LiquidAI/lfm2-12b-rag.py
# Draft — not smoke-tested
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.LiquidAI._liquid_common import load_liquid, run_chat

MODEL_KEY = "liquid-rag"
CONTEXT_PATH = Path("/app/scripts/read-only/init_neo4j.py")


def main() -> None:
    llm = load_liquid(MODEL_KEY)
    context = CONTEXT_PATH.read_text(encoding="utf-8")[:2000]
    messages = [
        {
            "role": "user",
            "content": (
                "Use only the context below to answer.\n\n"
                f"### Context\n{context}\n\n"
                "### Question\nWhat database does this script set up?"
            ),
        }
    ]
    print("Generating...\n")
    print(run_chat(llm, messages, temperature=0.1, top_p=0.1, max_tokens=256))
    del llm


if __name__ == "__main__":
    main()
