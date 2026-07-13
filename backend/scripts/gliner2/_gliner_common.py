"""Shared helpers for GLiNER2 local model loading."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal

from download_models2 import expected_gliner2_path, verify_pretrained_model_dir

MapLocation = Literal["cuda", "cpu"]


def require_gliner2() -> Path:
    path = expected_gliner2_path()
    try:
        verify_pretrained_model_dir(path)
    except FileNotFoundError as exc:
        print(f"GLiNER2 model not available: {exc}", file=sys.stderr)
        sys.exit(1)
    return path


def load_gliner2(*, map_location: MapLocation = "cuda") -> Any:
    """Load GLiNER2 from MODEL_PATH/GLiNER2 (never from hub id at runtime)."""
    from gliner2 import GLiNER2

    path = require_gliner2()
    print(f"Loading GLiNER2 from {path}...")
    return GLiNER2.from_pretrained(str(path), map_location=map_location)


def extract_with_gliner(
    extractor: Any,
    text: str,
    labels: list[str],
    *,
    nlp: Any | None = None,
) -> dict[str, Any]:
    """Run spaCy + GLiNER2 entity extraction; print both result lines."""
    if nlp is None:
        import spacy

        nlp = spacy.load("en_core_web_sm")
    doc = nlp(text)
    spacy_ents = [(ent.text, ent.label_) for ent in doc.ents]
    gliner_result = extractor.extract_entities(text, labels)
    print("spaCy Entities:", spacy_ents)
    print("GLiNER2 Entities:", gliner_result)
    return gliner_result
