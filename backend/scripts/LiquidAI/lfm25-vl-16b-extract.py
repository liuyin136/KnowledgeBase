# Run: docker compose exec api-worker python /app/scripts/LiquidAI/lfm25-vl-16b-extract.py
# Draft — not smoke-tested
# Multimodal API may need adjustment if llama-cpp chat handler lacks LFM-VL support.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.Jina._jina_common import PIC_DIR, require_assets
from scripts.LiquidAI._liquid_common import load_liquid, run_chat

IMAGE = PIC_DIR / "good_product.jpg"


def main() -> None:
    require_assets([IMAGE])
    llm = load_liquid("liquid-vl-extract", mmproj_key="liquid-vl-mmproj")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Extract product metadata as JSON from this image."},
                {"type": "image_url", "image_url": {"url": IMAGE.as_uri()}},
            ],
        }
    ]
    print("Generating...\n")
    print(run_chat(llm, messages, temperature=0.1, max_tokens=512))
    del llm


if __name__ == "__main__":
    main()
