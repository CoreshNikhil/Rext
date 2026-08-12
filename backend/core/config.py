"""Backend configuration, separate from MeterVision's config/settings.py.

Reads the same root .env file as the vision module, but owns a distinct set
of concerns (auth, database, scheduling) so the two modules never have to
coordinate which one "owns" a given setting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    ENVIRONMENT: str = "development"

    DATABASE_URL: str = f"sqlite:///{REPO_ROOT / 'backend' / 'gastool.db'}"

    SECRET_KEY: str
    ACCESS_TOKEN_TTL_MINUTES: int = 30
    REFRESH_TOKEN_TTL_DAYS_RESIDENT: int = 14
    REFRESH_TOKEN_TTL_DAYS_ADMIN: int = 7

    OTP_EXPIRY_MINUTES: int = 5
    OTP_MAX_ATTEMPTS: int = 5

    # NoDecode: pydantic-settings otherwise tries to JSON-parse env values
    # for any "complex" (non-scalar) field type before our own validator
    # ever sees them, which fails on a plain comma-separated string. This
    # opts CORS_ORIGINS out of that pre-parse so `_split_comma_separated`
    # is the only thing that ever interprets the raw value.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:8501"])

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_comma_separated(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def _validate_secret_key_length(cls, v: str) -> str:
        if len(v.encode("utf-8")) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 bytes long. Generate one with: "
                'python3 -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        return v


settings = Settings()
