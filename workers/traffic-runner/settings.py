"""Env validation. Fails fast at startup on missing/malformed variables."""
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    stable_url: AnyHttpUrl = "http://stable:8000"  # type: ignore[assignment]
    canary_url: AnyHttpUrl = "http://canary:8000"  # type: ignore[assignment]
    supabase_url: AnyHttpUrl
    supabase_service_key: str
    run_once: bool = False
    interval_seconds: int = 30

    @field_validator("supabase_service_key")
    @classmethod
    def _key_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("SUPABASE_SERVICE_KEY must not be empty")
        return v


try:
    cfg = Settings()
except Exception as exc:
    import sys as _sys
    print(f"\n❌  Missing or invalid environment variables:\n{exc}\n", file=_sys.stderr)
    _sys.exit(1)

STABLE = str(cfg.stable_url).rstrip("/")
CANARY = str(cfg.canary_url).rstrip("/")
SUPABASE_URL = str(cfg.supabase_url)
SUPABASE_KEY = cfg.supabase_service_key
RUN_ONCE = cfg.run_once
INTERVAL_SECONDS = cfg.interval_seconds
