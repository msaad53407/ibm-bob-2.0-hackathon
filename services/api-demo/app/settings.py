"""Env validation. Fails fast at startup on missing/malformed variables."""
import sys
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bug_profile: Literal["stable", "canary"] = "stable"
    port: int = 8000


try:
    cfg = Settings()
except Exception as exc:
    print(f"\n❌  Invalid environment variables:\n{exc}\n", file=sys.stderr)
    sys.exit(1)

BUG_PROFILE = cfg.bug_profile
