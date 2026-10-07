from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://search:search@localhost:5432/search"
    elasticsearch_url: str = "http://localhost:9200"
    es_index: str = "documents"
    csv_path: Path = Path("data/posts.csv")
    load_on_startup: bool = True
    search_limit: int = 20
    # Dataset is 1500 rows. The window must cover every hit: Elasticsearch
    # returns matches ordered by score, and the date sort happens in Postgres.
    es_match_window: int = 10_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
