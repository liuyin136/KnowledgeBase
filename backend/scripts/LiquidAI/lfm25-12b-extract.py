# Run: docker compose exec api-worker python /app/scripts/LiquidAI/lfm25-12b-extract.py
# Draft — not smoke-tested
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.LiquidAI._liquid_common import load_liquid, run_chat

MODEL_KEY = "liquid-extract"


def main() -> None:
    llm = load_liquid(MODEL_KEY)
    messages = [
        {
            "role": "user",
            "content": "Extract as YAML:\nName: Ada Lovelace\nBorn: 1815\nField: Computing",
        }
    ]
    print("Generating...\n")
    print(run_chat(llm, messages, max_tokens=256))
    del llm


if __name__ == "__main__":
    main()
