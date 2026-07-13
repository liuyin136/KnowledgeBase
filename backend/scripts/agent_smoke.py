#!/usr/bin/env python3
"""Pre-BUILD/DEBUG smoke checks for agent sessions.

Usage (from project root):

  docker compose run --rm api-worker python scripts/agent_smoke.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BACKEND_HEALTH_URL = os.environ.get("AGENT_SMOKE_HEALTH_URL", "http://backend:8000/health")


def check_health() -> tuple[bool, str]:
    try:
        req = urllib.request.Request(BACKEND_HEALTH_URL, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return False, f"health status {resp.status}"
            return True, "ok"
    except urllib.error.URLError as exc:
        return False, f"health unreachable: {exc}"
    except Exception as exc:
        return False, f"health error: {exc}"


def check_imports() -> tuple[bool, str]:
    try:
        from app.workers.tasks import hybrid_search  # noqa: F401
        from app.services.neo4j_client import get_neo4j_client

        client = get_neo4j_client()
        assert hasattr(client, "delete_ingestion_tree_for_source")
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def check_vault_db() -> tuple[bool, str]:
    try:
        from app.services import vault_db

        vault_db.init_vault_db()
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def check_gpu_optional() -> tuple[bool, str]:
    try:
        import torch

        if not torch.cuda.is_available():
            return True, "skipped (no CUDA)"
        return True, f"cuda device={torch.cuda.get_device_name(0)}"
    except ImportError:
        return True, "skipped (torch not installed)"
    except Exception as exc:
        return True, f"skipped ({exc})"


def check_extraction_models_optional() -> tuple[bool, str]:
    """Optional: GLiNER2 + Qwen3 local dirs and package imports (post 2.01 prep rebuild)."""
    try:
        from pathlib import Path

        import bitsandbytes  # noqa: F401
        import gliner2  # noqa: F401
        import transformers  # noqa: F401

        model_root = Path(os.environ.get("MODEL_PATH", "/app/models"))
        gliner = model_root / "GLiNER2" / "config.json"
        qwen3 = model_root / "Qwen3-8B" / "config.json"
        missing = [p for p in (gliner, qwen3) if not p.is_file()]
        if missing:
            return True, f"skipped (missing after rebuild: {', '.join(str(p) for p in missing)})"
        return True, "gliner2+qwen3 paths ok"
    except ImportError as exc:
        return True, f"skipped ({exc})"
    except Exception as exc:
        return True, f"skipped ({exc})"


def main() -> int:
    checks: list[tuple[str, tuple[bool, str]]] = [
        ("backend_health", check_health()),
        ("imports", check_imports()),
        ("vault_db", check_vault_db()),
        ("gpu_optional", check_gpu_optional()),
        ("extraction_models_optional", check_extraction_models_optional()),
    ]
    failed = [name for name, (ok, _) in checks if not ok]
    report = {name: {"ok": ok, "detail": detail} for name, (ok, detail) in checks}
    print(json.dumps(report, indent=2))
    if failed:
        print(f"FAIL: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("agent_smoke: all required checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
