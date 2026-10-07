from datetime import datetime, timedelta

import pytest

from tests.helpers import record, store


@pytest.mark.asyncio
async def test_search_returns_newest_matches_not_highest_score(client, application):
    # Twenty short documents score higher than one long, newer document.
    # A search that keeps only the Elasticsearch top-20 by BM25 drops that newer row.
    base = datetime(2019, 1, 1, 12, 0, 0)
    records = [
        record(document_id, "альфамаркер", base + timedelta(days=document_id - 1))
        for document_id in range(1, 21)
    ]
    records.append(
        record(
            21,
            "альфамаркер " + ("заполнитель " * 2000),
            datetime(2019, 12, 31, 12, 0, 0),
        )
    )
    records.append(record(22, "совсем другой текст без маркера", datetime(2019, 12, 30, 12, 0, 0)))
    await store(application, records)

    response = await client.get("/documents/search", params={"text": "альфамаркер"})

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [21, *range(20, 1, -1)]
    assert body[0]["rubrics"] == ["rubric-21"]
    assert body[0]["text"].startswith("альфамаркер ")
    assert body[0]["created_date"] == "2019-12-31T12:00:00"
    created = [item["created_date"] for item in body]
    assert created == sorted(created, reverse=True)

    upper = await client.get("/documents/search", params={"text": "АЛЬФАМАРКЕР"})
    assert [item["id"] for item in upper.json()] == [21, *range(20, 1, -1)]


@pytest.mark.asyncio
async def test_search_uses_russian_stemming(client, application):
    await store(
        application,
        [record(1, "Объявлен конкурс на новый скин", datetime(2019, 6, 1, 10, 0, 0))],
    )

    response = await client.get("/documents/search", params={"text": "конкурсы"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [1]


@pytest.mark.asyncio
async def test_search_requires_every_term(client, application):
    await store(
        application,
        [
            record(1, "только конкурс", datetime(2019, 6, 2, 10, 0, 0)),
            record(2, "конкурс и новый скин", datetime(2019, 6, 3, 10, 0, 0)),
        ],
    )

    response = await client.get("/documents/search", params={"text": "конкурс скин"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [2]


@pytest.mark.asyncio
async def test_search_without_matches_is_empty(client):
    response = await client.get("/documents/search", params={"text": "несуществующеесловоxyz"})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_search_rejects_blank_query(client):
    missing = await client.get("/documents/search")
    blank = await client.get("/documents/search", params={"text": "   "})
    assert missing.status_code == 422
    assert blank.status_code == 422


@pytest.mark.asyncio
async def test_delete_removes_document_from_database_and_index(client, application):
    await store(
        application,
        [
            record(5, "бетамаркер старый", datetime(2019, 3, 1, 8, 0, 0)),
            record(6, "бетамаркер новый", datetime(2019, 8, 1, 8, 0, 0)),
        ],
    )

    deleted = await client.delete("/documents/6")
    assert deleted.status_code == 204
    assert deleted.content == b""

    response = await client.get("/documents/search", params={"text": "бетамаркер"})
    assert [item["id"] for item in response.json()] == [5]

    missing = await client.delete("/documents/6")
    unknown = await client.delete("/documents/999")
    assert missing.status_code == 404
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
