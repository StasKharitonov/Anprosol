import ast
import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from elasticsearch import AsyncElasticsearch
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.es import count_index, drop_index, ensure_index, index_documents
from app.models import Document

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentRecord:
    id: int
    text: str
    created_date: datetime
    rubrics: list[str]


def parse_rubrics(raw: str) -> list[str]:
    value = ast.literal_eval(raw)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("rubrics column must be a list of strings")
    return value


def read_csv(path: Path) -> list[DocumentRecord]:
    records: list[DocumentRecord] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = {"text", "created_date", "rubrics"} - columns
        if missing:
            raise ValueError(f"csv is missing columns: {sorted(missing)}")
        for document_id, row in enumerate(reader, start=1):
            records.append(
                DocumentRecord(
                    id=document_id,
                    text=row["text"],
                    created_date=datetime.strptime(row["created_date"], "%Y-%m-%d %H:%M:%S"),
                    rubrics=parse_rubrics(row["rubrics"]),
                )
            )
    return records


async def count_documents(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(Document))
    return int(result.scalar_one())


async def insert_records(
    sessionmaker: async_sessionmaker,
    records: list[DocumentRecord],
) -> None:
    async with sessionmaker() as session:
        session.add_all(
            [
                Document(
                    id=record.id,
                    text=record.text,
                    rubrics=record.rubrics,
                    created_date=record.created_date,
                )
                for record in records
            ]
        )
        await session.commit()


async def rebuild_index(
    sessionmaker: async_sessionmaker,
    client: AsyncElasticsearch,
    index: str,
) -> None:
    await drop_index(client, index)
    await ensure_index(client, index)
    async with sessionmaker() as session:
        result = await session.execute(select(Document.id, Document.text))
        pairs = [(document_id, text) for document_id, text in result.all()]
    await index_documents(client, index, pairs)
    log.info("rebuilt index %s from %s database rows", index, len(pairs))


async def load_csv(
    sessionmaker: async_sessionmaker,
    client: AsyncElasticsearch,
    index: str,
    path: Path,
) -> int:
    records = read_csv(path)
    await insert_records(sessionmaker, records)
    await index_documents(client, index, [(record.id, record.text) for record in records])
    log.info("loaded %s documents from %s", len(records), path)
    return len(records)


async def ensure_data(
    sessionmaker: async_sessionmaker,
    client: AsyncElasticsearch,
    index: str,
    csv_path: Path,
    *,
    load_on_startup: bool,
) -> None:
    if not load_on_startup:
        return

    async with sessionmaker() as session:
        db_count = await count_documents(session)

    if db_count == 0:
        if not csv_path.is_file():
            log.warning("csv file %s is missing, database stays empty", csv_path)
            return
        await load_csv(sessionmaker, client, index, csv_path)
        return

    indexed = await count_index(client, index)
    if indexed != db_count:
        log.warning(
            "index %s has %s documents, database has %s; rebuilding the index",
            index,
            indexed,
            db_count,
        )
        await rebuild_index(sessionmaker, client, index)
