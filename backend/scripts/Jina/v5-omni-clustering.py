# Run: docker compose exec api-worker python /app/scripts/Jina/v5-omni-clustering.py
import sys
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.Jina._jina_common import (
    PDF_DIR,
    PIC_DIR,
    embed_image,
    embed_pdf_page,
    embed_text,
    load_jina_text,
    require_assets,
)

TASK = "clustering"
ASSETS = [
    PIC_DIR / "mars.jpg",
    PIC_DIR / "jupiter.jpg",
    PDF_DIR / "mars_doc.pdf",
    PDF_DIR / "jupiter_doc.pdf",
]

TEXT_ITEMS = [
    "Mars is the Red Planet.",
    "Jupiter is a gas giant.",
]
IMAGE_ITEMS = [ASSETS[0], ASSETS[1]]
PDF_ITEMS = [ASSETS[2], ASSETS[3]]


def main() -> None:
    require_assets(ASSETS)

    embeddings = []
    labels = []

    llm = load_jina_text(TASK)
    for text in TEXT_ITEMS:
        embeddings.append(embed_text(llm, text))
        labels.append(f"text:{text[:20]}")
    del llm

    for path in IMAGE_ITEMS:
        embeddings.append(embed_image(TASK, path))
        labels.append(f"image:{str(path)[:20]}")
    for path in PDF_ITEMS:
        embeddings.append(embed_pdf_page(TASK, path))
        labels.append(f"pdf:{str(path)[:20]}")

    emb_matrix = np.vstack(embeddings).astype(np.float32)
    sim_matrix = emb_matrix @ emb_matrix.T

    print("=== Clustering Similarity Matrix (higher = more similar) ===")
    for i, lab in enumerate(labels):
        print(f"{lab}: {sim_matrix[i]}")

    kmeans = KMeans(n_clusters=2, random_state=42).fit(emb_matrix)
    print("\nKMeans labels (2 clusters):", kmeans.labels_)


if __name__ == "__main__":
    main()
