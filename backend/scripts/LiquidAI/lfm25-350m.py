# Run: docker compose exec api-worker python /app/scripts/LiquidAI/lfm25-350m.py
# Draft — not smoke-tested
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.LiquidAI._liquid_common import load_liquid, run_chat

MODEL_KEY = "liquid-350m"


def main() -> None:
    llm = load_liquid(MODEL_KEY)
    
    print(f"Is Flash Attention actively running? ")
    messages = [
        {
            "role": "user",
            "content": (
                "Extract fields as JSON from: Order #42, customer Jane Doe, "
                "item Widget Pro, qty 3."
            ),
        }
    ]
    print("Generating...\n")
    print(run_chat(llm, messages, max_tokens=256))
    del llm


if __name__ == "__main__":
    main()
