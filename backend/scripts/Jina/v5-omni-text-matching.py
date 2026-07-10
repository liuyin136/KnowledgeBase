# Run: docker compose exec api-worker python /app/scripts/Jina/v5-omni-text-matching.py
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

TASK = "text-matching"
ASSETS = [
    PIC_DIR / "mars.jpg",
    PIC_DIR / "mars_close.jpg",
    PIC_DIR / "jupiter.jpg",
    PDF_DIR / "mars_doc.pdf",
    PDF_DIR / "mars_doc2.pdf",
    PDF_DIR / "jupiter_doc.pdf",
]


def main() -> None:
    require_assets(ASSETS)
    llm = load_jina_text(TASK)

    texts = [
        "Mars is known as the Red Planet.",
        "The Red Planet refers to Mars.",
        "Jupiter has many moons.",
        "The weather is nice today.",
    ]
    t_embs = [embed_text(llm, t) for t in texts]
    del llm

    i_embs = [
        embed_image(TASK, ASSETS[0]),
        embed_image(TASK, ASSETS[1]),
        embed_image(TASK, ASSETS[2]),
    ]
    p_embs = [
        embed_pdf_page(TASK, ASSETS[3]),
        embed_pdf_page(TASK, ASSETS[4]),
        embed_pdf_page(TASK, ASSETS[5]),
    ]

    print("=== Text-Matching Similarity Scores ===")
    print(f"Text pair 0-1 (Mars paraphrase): {cosine_sim(t_embs[0], t_embs[1]):.4f}")
    print(f"Text pair 0-2 (unrelated): {cosine_sim(t_embs[0], t_embs[2]):.4f}")
    print(f"Image pair 0-1 (similar Mars): {cosine_sim(i_embs[0], i_embs[1]):.4f}")
    print(f"Image pair 0-2 (unrelated): {cosine_sim(i_embs[0], i_embs[2]):.4f}")
    print(f"PDF pair 0-1 (similar Mars doc): {cosine_sim(p_embs[0], p_embs[1]):.4f}")
    print(f"PDF pair 0-2 (unrelated): {cosine_sim(p_embs[0], p_embs[2]):.4f}")


if __name__ == "__main__":
    main()
