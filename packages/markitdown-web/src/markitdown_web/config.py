from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import os

try:  # Python 3.11+
    import tomllib as tomli  # type: ignore
except Exception:  # pragma: no cover
    import tomli  # type: ignore


@dataclass(frozen=True)
class WebConfig:
    api_key: str
    max_upload_mb: int = 10
    enable_plugins: bool = False
    log_level: str = "info"
    cors_origins: Optional[list[str]] = None

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb) * 1024 * 1024


def _env_bool(name: str, default: Optional[bool]) -> Optional[bool]:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def load_config(config_path: Optional[str] = None) -> WebConfig:
    # Determine config path: explicit argument, or env, else optional default in CWD
    cfg_path = (
        config_path
        or os.getenv("MARKITDOWN_WEB_CONFIG")
        or (os.path.join(os.getcwd(), "markitdown_web.toml"))
    )

    data: dict = {}
    if os.path.isfile(cfg_path):
        with open(cfg_path, "rb") as f:
            data = tomli.load(f) or {}

    # Read config file values
    api_key = str(data.get("api_key") or "").strip()
    max_upload_mb = int(data.get("max_upload_mb") or 10)
    enable_plugins = bool(data.get("enable_plugins") or False)
    log_level = str(data.get("log_level") or "info")
    cors_origins = data.get("cors_origins")
    if cors_origins is not None and not isinstance(cors_origins, list):
        cors_origins = None

    # Environment overrides
    api_key = os.getenv("MARKITDOWN_WEB_API_KEY", api_key)
    max_upload_mb = int(os.getenv("MARKITDOWN_WEB_MAX_UPLOAD_MB", max_upload_mb))
    enable_plugins = _env_bool("MARKITDOWN_ENABLE_PLUGINS", enable_plugins) or False
    log_level = os.getenv("MARKITDOWN_WEB_LOG_LEVEL", log_level)
    cors_env = os.getenv("MARKITDOWN_WEB_CORS_ORIGINS")
    if cors_env:
        cors_origins = [s.strip() for s in cors_env.split(",") if s.strip()]

    if not api_key:
        # Require an API key for v1 per requirements
        raise RuntimeError(
            "MARKITDOWN_WEB_API_KEY is required (or set api_key in markitdown_web.toml)"
        )

    return WebConfig(
        api_key=api_key,
        max_upload_mb=max_upload_mb,
        enable_plugins=enable_plugins,
        log_level=log_level,
        cors_origins=cors_origins,
    )
