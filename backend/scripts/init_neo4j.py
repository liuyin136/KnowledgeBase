"""Convenience wrapper — delegates to scripts/read-only/init_neo4j.py."""
from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "read-only" / "init_neo4j.py"
    runpy.run_path(str(target), run_name="__main__")
