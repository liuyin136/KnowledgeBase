from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    data_root: str = "/data"
    redis_url: str = "redis://redis:6379/0"
    rq_queue_name: str = "default"
    file_cache_ttl: int = 3600
    file_cache_max_bytes: int = 1_048_576
    frontend_origin: str = "*"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings(
        data_root=os.environ.get("DATA_ROOT", "/data"),
        redis_url=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        rq_queue_name=os.environ.get("RQ_QUEUE_NAME", "default"),
        file_cache_ttl=int(os.environ.get("FILE_CACHE_TTL", "3600")),
        file_cache_max_bytes=int(os.environ.get("FILE_CACHE_MAX_BYTES", "1048576")),
        frontend_origin=os.environ.get("FRONTEND_ORIGIN", "*"),
    )
