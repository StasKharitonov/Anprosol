from elasticsearch import AsyncElasticsearch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.es import delete_from_index, search_ids
from app.models import Document


class DocumentNotFound(Exception):
    def __init__(self, document_id: int) -> None:
        self.document_id = document_id
        super().__init__(f"document {document_id} was not found")


class MatchWindowExceeded(Exception):
    def __init__(self, total: int, window: int) -> None:
        self.total = total
        self.window = window
        super().__init__(
            f"query matched {total} documents, which is above the fetch window of {window}"
        )


async def search_documents(
    session: AsyncSession,
    client: AsyncElasticsearch,
    settings: Settings,
    text: str,
) -> list[Document]:
    """Find documents by text in Elasticsearch, then take the newest rows from Postgres.

    The index stores only id and text, so created_date cannot be a sort key there.
    Taking the top hits by BM25 and re-sorting those would drop a newer match that
    scored worse than an older one. Ids are collected first, then ordered in the database.
    """
    ids, total = await search_ids(
        client,
        settings.es_index,
        text,
        settings.es_match_window,
    )
    if total > len(ids):
        raise MatchWindowExceeded(total, settings.es_match_window)
    if not ids:
        return []

    result = await session.execute(
        select(Document)
        .where(Document.id.in_(ids))
        .order_by(Document.created_date.desc(), Document.id.desc())
        .limit(settings.search_limit)
    )
    return list(result.scalars().all())


async def delete_document(
    session: AsyncSession,
    client: AsyncElasticsearch,
    index: str,
    document_id: int,
) -> None:
    document = await session.get(Document, document_id)
    if document is None:
        raise DocumentNotFound(document_id)

    # Index first, database second. A crash between the two leaves the row in
    # Postgres and out of the index; the next startup rebuilds the index when
    # the counts diverge. Search reads fields from Postgres, so a row that is
    # already gone cannot appear in the response.
    await delete_from_index(client, index, document_id)
    await session.delete(document)
    await session.commit()
