from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    anthropic_api_key: str
    embedding_model_name: str = "google/embeddinggemma-300m"
    chunk_size: int = 512
    chunk_overlap: int = 50
    max_context_tokens: int = 4000
    retrieval_max_steps: int = 4

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
