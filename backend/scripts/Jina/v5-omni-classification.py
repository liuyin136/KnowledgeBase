# Run: docker compose exec api-worker python /app/scripts/Jina/v5-omni-classification.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.Jina._jina_common import (
    PDF_DIR,
    PIC_DIR,
    cosine_sim,
    embed_image,
    embed_pdf_page,
    embed_text,
    load_jina_text,
    require_assets,
)

TASK = "classification"
ASSETS = [
    PIC_DIR / "good_product.jpg",
    PIC_DIR / "broken_product.jpg",
    PDF_DIR / "positive_review.pdf",
    PDF_DIR / "negative_review.pdf",
]


def main() -> None:
    require_assets(ASSETS)
    llm = load_jina_text(TASK)

    class_texts = [
        "I love this product, it works perfectly!",
        "This is the best purchase I have ever made.",
        "The item arrived broken and is useless.",
        "Terrible quality, do not buy.",
    ]
    t_embs = [embed_text(llm, t) for t in class_texts]
    del llm

    i_embs = [
        embed_image(TASK, ASSETS[0]),
        embed_image(TASK, ASSETS[1]),
    ]
    p_embs = [
        embed_pdf_page(TASK, ASSETS[2]),
        embed_pdf_page(TASK, ASSETS[3]),
    ]

    print("=== Classification Similarity Scores ===")
    print(f"Text Pos-Pos: {cosine_sim(t_embs[0], t_embs[1]):.4f}")
    print(f"Text Pos-Neg: {cosine_sim(t_embs[0], t_embs[2]):.4f}")
    print(f"Image Good-Bad: {cosine_sim(i_embs[0], i_embs[1]):.4f}")
    print(f"PDF Good-Bad: {cosine_sim(p_embs[0], p_embs[1]):.4f}")


if __name__ == "__main__":
    main()
