from __future__ import annotations

import subprocess


def check_gpu_available() -> None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("nvidia-smi not found — GPU worker requires NVIDIA drivers") from exc
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"GPU check failed: {result.stderr.strip() or 'no GPU detected'}")


def get_vram_used_mb() -> int:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            return 0
        line = result.stdout.strip().splitlines()[0].strip()
        return int(line)
    except (FileNotFoundError, ValueError, IndexError):
        return 0
