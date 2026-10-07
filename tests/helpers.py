from datetime import datetime

from app.es import index_documents
from app.loader import DocumentRecord, insert_records


def record(document_id: int, text: str, created_date: datetime) -> DocumentRecord:
    return DocumentRecord(
        id=document_id,
        text=text,
        created_date=created_date,
        rubrics=[f"rubric-{document_id}"],
    )


async def store(application, records: list[DocumentRecord]) -> None:
    await insert_records(application.state.sessionmaker, records)
    await index_documents(
        application.state.es,
        application.state.settings.es_index,
        [(item.id, item.text) for item in records],
    )
