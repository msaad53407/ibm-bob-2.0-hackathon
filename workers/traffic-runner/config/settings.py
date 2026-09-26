"""Env validation. Fails fast at startup on missing/malformed variables."""
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    stable_url: AnyHttpUrl = "http://stable:8000"  # type: ignore[assignment]
    canary_url: AnyHttpUrl = "http://canary:8000"  # type: ignore[assignment]
    supabase_url: AnyHttpUrl
    supabase_service_key: str
    admin_token: str
    openrouter_api_key: str = ""
    llm_model: str = "deepseek/deepseek-v4.1-flash"
    llm_timeout_seconds: float = 60.0
    port: int = 8004
    run_once: bool = False
    run_on_start: bool = True
    interval_seconds: int = 30

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

STABLE = str(cfg.stable_url).rstrip("/")
CANARY = str(cfg.canary_url).rstrip("/")
SUPABASE_URL = str(cfg.supabase_url)
SUPABASE_KEY = cfg.supabase_service_key
ADMIN_TOKEN = cfg.admin_token
OPENROUTER_API_KEY = cfg.openrouter_api_key.strip()
LLM_MODEL = cfg.llm_model.strip() or "deepseek/deepseek-v4.1-flash"
LLM_TIMEOUT = cfg.llm_timeout_seconds
PORT = cfg.port
RUN_ONCE = cfg.run_once
RUN_ON_START = cfg.run_on_start
INTERVAL_SECONDS = cfg.interval_seconds
