# Run: docker compose exec api-worker python /app/scripts/LiquidAI/lfm25-8b-a1b.py
# Draft — not smoke-tested
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.LiquidAI._liquid_common import load_liquid, run_chat

MODEL_KEY = "liquid-8b"


def main() -> None:
    llm = load_liquid(MODEL_KEY)
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain MoE in one sentence."},
    ]
    print("Generating...\n")
    print(run_chat(llm, messages, max_tokens=128))
    del llm


if __name__ == "__main__":
    main()
