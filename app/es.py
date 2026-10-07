import logging

from elasticsearch import AsyncElasticsearch, NotFoundError
from elasticsearch.helpers import async_bulk

log = logging.getLogger(__name__)

MAPPINGS = {
    "properties": {
        "id": {"type": "integer"},
        "text": {"type": "text", "analyzer": "russian"},
    }
}


def make_client(url: str) -> AsyncElasticsearch:
    return AsyncElasticsearch(url, request_timeout=60)


async def ensure_index(client: AsyncElasticsearch, index: str) -> None:
    if await client.indices.exists(index=index):
        return
    await client.indices.create(index=index, mappings=MAPPINGS)


async def index_documents(
    client: AsyncElasticsearch,
    index: str,
    documents: list[tuple[int, str]],
) -> None:
    if not documents:
        return

    def actions():
        for document_id, text in documents:
            yield {
                "_op_type": "index",
                "_index": index,
                "_id": document_id,
                "_source": {"id": document_id, "text": text},
            }

    success, errors = await async_bulk(
        client,
        actions(),
        refresh="wait_for",
        raise_on_error=False,
    )
    if errors:
        log.error("failed to index %s documents: %s", len(errors), errors[:3])
        raise RuntimeError(f"elasticsearch bulk index failed for {len(errors)} documents")
    log.info("indexed %s documents into %s", success, index)


async def delete_from_index(client: AsyncElasticsearch, index: str, document_id: int) -> None:
    try:
        await client.delete(index=index, id=str(document_id), refresh="wait_for")
    except NotFoundError:
        return


async def search_ids(
    client: AsyncElasticsearch,
    index: str,
    text: str,
    window: int,
) -> tuple[list[int], int]:
    response = await client.search(
        index=index,
        query={"match": {"text": {"query": text, "operator": "and"}}},
        source_includes=["id"],
        size=window,
        track_total_hits=True,
    )
    hits = response["hits"]["hits"]
    total_payload = response["hits"]["total"]
    total = int(total_payload["value"] if isinstance(total_payload, dict) else total_payload)
    ids: list[int] = []
    for hit in hits:
        source = hit.get("_source") or {}
        raw_id = source.get("id", hit["_id"])
        ids.append(int(raw_id))
    return ids, total


async def count_index(client: AsyncElasticsearch, index: str) -> int:
    response = await client.count(index=index)
    return int(response["count"])


async def drop_index(client: AsyncElasticsearch, index: str) -> None:
    await client.indices.delete(index=index, ignore_unavailable=True)
