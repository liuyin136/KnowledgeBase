# Run: docker compose exec api-worker python /app/scripts/LiquidAI/lfm25-12b-instruct.py
# Draft — not smoke-tested
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.LiquidAI._liquid_common import load_liquid, run_chat

MODEL_KEY = "liquid-instruct"


def main() -> None:
    llm = load_liquid(MODEL_KEY)
    messages = [
        {"role": "system", "content": "You are a helpful assistant trained by Liquid AI."},
        {"role": "user", "content": "What is C. elegans?"},
    ]
    print("Generating...\n")
    print(run_chat(llm, messages, temperature=0.1, top_p=0.1, max_tokens=256))
    del llm


if __name__ == "__main__":
    main()
