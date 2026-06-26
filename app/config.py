from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().with_name(".env")


class Settings(BaseSettings):
    database_url: str
    gemini_api_key: str
    embedding_model_name: str = "google/embeddinggemma-300m"
    chunk_size: int = 512
    chunk_overlap: int = 50
    max_context_tokens: int = 4000
    retrieval_max_steps: int = 4

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
