"""Configurable project, region and model settings."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
FIXTURES_DIR = PACKAGE_ROOT / "fixtures"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_cloud_project: str = Field(default="", alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field(default="us-central1", alias="GOOGLE_CLOUD_LOCATION")
    google_genai_model: str = Field(default="gemini-2.0-flash", alias="GOOGLE_GENAI_MODEL")
    google_genai_use_vertexai: bool = Field(default=True, alias="GOOGLE_GENAI_USE_VERTEXAI")
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    staging_bucket: str = Field(default="", alias="STAGING_BUCKET")
    agent_engine_resource_name: str = Field(default="", alias="AGENT_ENGINE_RESOURCE_NAME")
    fixtures_dir: Path = Field(default=FIXTURES_DIR)

    @property
    def model_name(self) -> str:
        return self.google_genai_model

    @property
    def has_credentials(self) -> bool:
        if self.google_api_key:
            return True
        if self.google_cloud_project and self.google_genai_use_vertexai:
            return True
        return bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
