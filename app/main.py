import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api import router
from app.config import Settings, get_settings
from app.db import init_db, make_engine, make_sessionmaker
from app.es import ensure_index, make_client
from app.loader import ensure_data

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent


async def wait_until_ready(engine: AsyncEngine, es, attempts: int = 30) -> None:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            if not await es.ping():
                raise ConnectionError("elasticsearch did not answer ping")
            return
        except Exception as exc:
            last_error = exc
            log.warning("dependencies are not ready, attempt %s/%s: %s", attempt, attempts, exc)
            await asyncio.sleep(2)
    raise RuntimeError("postgres or elasticsearch is not ready") from last_error


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(app.state.settings.database_url)
        sessionmaker = make_sessionmaker(engine)
        es = make_client(app.state.settings.elasticsearch_url)
        app.state.engine = engine
        app.state.sessionmaker = sessionmaker
        app.state.es = es
        try:
            await wait_until_ready(engine, es)
            await init_db(engine)
            await ensure_index(es, app.state.settings.es_index)
            await ensure_data(
                sessionmaker,
                es,
                app.state.settings.es_index,
                app.state.settings.csv_path,
                load_on_startup=app.state.settings.load_on_startup,
            )
            yield
        finally:
            await es.close()
            await engine.dispose()

    app = FastAPI(
        title="Поиск документов",
        version="1.0.0",
        summary="Полнотекстовый поиск по текстам документов",
        description=(
            "Документы хранятся в PostgreSQL. Поиск выполняется по полю text в Elasticsearch, "
            "в ответ возвращаются не более 20 совпадений со всеми полями базы, "
            "отсортированные по created_date от новых к старым."
        ),
        servers=[{"url": "http://localhost:8000"}],
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.docs_path = ROOT / "docs.json"
    app.include_router(router)
    return app


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
app = create_app()
