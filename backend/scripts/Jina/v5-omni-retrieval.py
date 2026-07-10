# Run: docker compose exec api-worker python /app/scripts/Jina/v5-omni-retrieval.py
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

TASK = "retrieval"
ASSETS = [
    PIC_DIR / "mars_red.jpg",
    PIC_DIR / "earth_blue.jpg",
    PDF_DIR / "mars_doc.pdf",
    PDF_DIR / "earth_blue.pdf",
]


def main() -> None:
    require_assets(ASSETS)
    llm = load_jina_text(TASK)

    t_q = embed_text(llm, "Query: Which planet is known as the Red Planet?")
    t_pos = embed_text(
        llm, "Document: Mars is often called the Red Planet due to its reddish appearance."
    )
    t_neg1 = embed_text(llm, "Document: Jupiter is the largest planet in our solar system.")
    t_neg2 = embed_text(llm, "Document: The sky is blue on a clear day.")
    del llm

    i_red = embed_image(TASK, ASSETS[0])
    i_blue = embed_image(TASK, ASSETS[1])
    p_red = embed_pdf_page(TASK, ASSETS[2])
    p_blue = embed_pdf_page(TASK, ASSETS[3])

    print("=== Retrieval Similarity Scores ===")
    print(f"Text-Pos (Mars): {cosine_sim(t_q, t_pos):.4f}")
    print(f"Text-Neg1 (Jupiter): {cosine_sim(t_q, t_neg1):.4f}")
    print(f"Text-Neg2 (Blue sky): {cosine_sim(t_q, t_neg2):.4f}")
    print(f"Image-Red (Mars): {cosine_sim(t_q, i_red):.4f}")
    print(f"Image-Blue (Earth): {cosine_sim(t_q, i_blue):.4f}")
    print(f"PDF-Red: {cosine_sim(t_q, p_red):.4f}")
    print(f"PDF-Blue: {cosine_sim(t_q, p_blue):.4f}")


if __name__ == "__main__":
    main()
