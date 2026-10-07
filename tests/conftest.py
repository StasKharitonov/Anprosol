import inspect
import os
from pathlib import Path

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.engine.url import make_url

from app.config import Settings
from app.main import create_app
from app.models import Document

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = "postgresql+asyncpg://search:search@localhost:5432/search_test"
DEFAULT_ELASTICSEARCH_URL = "http://localhost:9200"


async def ensure_database(database_url: str) -> None:
    url = make_url(database_url)
    connection = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port or 5432,
        database="postgres",
    )
    try:
        exists = await connection.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            url.database,
        )
        if not exists:
            await connection.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await connection.close()


async def reset_storage(application) -> None:
    async with application.state.sessionmaker() as session:
        await session.execute(delete(Document))
        await session.commit()
    await application.state.es.delete_by_query(
        index=application.state.settings.es_index,
        query={"match_all": {}},
        refresh=True,
        conflicts="proceed",
    )


@pytest.fixture(scope="session")
async def application():
    database_url = os.environ.get("TEST_DATABASE_URL", DEFAULT_DATABASE_URL)
    await ensure_database(database_url)
    settings = Settings(
        database_url=database_url,
        elasticsearch_url=os.environ.get("TEST_ELASTICSEARCH_URL", DEFAULT_ELASTICSEARCH_URL),
        es_index="documents_test",
        csv_path=ROOT / "data" / "posts.csv",
        load_on_startup=False,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def client(application):
    await reset_storage(application)
    transport_kwargs = {}
    if "lifespan" in inspect.signature(ASGITransport).parameters:
        transport_kwargs["lifespan"] = "off"
    transport = ASGITransport(app=application, **transport_kwargs)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


