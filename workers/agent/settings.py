"""Env validation. Fails fast at startup on missing/malformed variables."""
import _paths  # noqa: F401 — ensures shared/ is importable (Docker + repo layouts)
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from verification import LATENCY_DEGRADATION_FACTOR as SPEC_LATENCY_FACTOR  # noqa: E402


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: AnyHttpUrl
    supabase_service_key: str
    admin_token: str
    proxy_admin_url: AnyHttpUrl = "http://proxy:8080/admin/route"  # type: ignore[assignment]
    port: int = 8003
    latency_degradation_factor: float = SPEC_LATENCY_FACTOR

    @field_validator("supabase_service_key")
    @classmethod
    def _key_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("SUPABASE_SERVICE_KEY must not be empty")
        return v

    @field_validator("admin_token")
    @classmethod
    def _token_not_empty(cls, v: str) -> str:
        if not v or not v.strip() or len(v.strip()) < 16:
            raise ValueError("ADMIN_TOKEN must be at least 16 chars")
        return v


try:
    cfg = Settings()
except Exception as exc:
    import sys as _sys
    print(f"\n❌  Missing or invalid environment variables:\n{exc}\n", file=_sys.stderr)
    _sys.exit(1)

SUPABASE_URL = str(cfg.supabase_url)
SUPABASE_KEY = cfg.supabase_service_key
ADMIN_TOKEN = cfg.admin_token
PROXY_ADMIN_URL = str(cfg.proxy_admin_url).rstrip("/")
LATENCY_DEGRADATION_FACTOR = cfg.latency_degradation_factor
PORT = cfg.port
