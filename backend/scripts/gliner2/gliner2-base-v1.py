"""Smoke demo: GLiNER2 entity extraction from local MODEL_PATH/GLiNER2."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.gliner2._gliner_common import extract_with_gliner, load_gliner2

TEXT = "Apple CEO Tim Cook announced iPhone 15 in China yesterday."
LABELS = ["company", "person", "product", "location", "date"]


def main() -> None:
    extractor = load_gliner2()
    try:
        extract_with_gliner(extractor, TEXT, LABELS)
    finally:
        del extractor


if __name__ == "__main__":
    main()
