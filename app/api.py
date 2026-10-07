from pathlib import Path
from typing import Annotated

from elasticsearch import ApiError
from elasticsearch import ConnectionError as ElasticsearchConnectionError
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.documents import DocumentNotFound, MatchWindowExceeded, delete_document, search_documents
from app.schemas import DocumentOut

router = APIRouter()
PAGE = Path(__file__).resolve().parent / "static" / "index.html"


@router.get("/", include_in_schema=False)
async def root() -> FileResponse:
    if not PAGE.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="page is missing")
    return FileResponse(PAGE)


@router.get("/docs.json", include_in_schema=False)
async def openapi_file(request: Request) -> FileResponse:
    path = request.app.state.docs_path
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="docs.json is missing")
    return FileResponse(path, media_type="application/json")


@router.get("/health", summary="Проверка зависимостей", operation_id="health")
async def health(request: Request) -> dict[str, str]:
    try:
        async with request.app.state.sessionmaker() as session:
            await session.execute(text("SELECT 1"))
        if not await request.app.state.es.ping():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="elasticsearch is unavailable",
            )
    except HTTPException:
        raise
    except (SQLAlchemyError, ElasticsearchConnectionError, ApiError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="dependency is unavailable",
        ) from exc
    return {"status": "ok"}


@router.get(
    "/documents/search",
    response_model=list[DocumentOut],
    summary="Найти документы по тексту",
    operation_id="searchDocuments",
    response_description="До 20 документов со всеми полями базы, от новых к старым",
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Совпадений больше, чем окно выборки из индекса",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Индекс недоступен"},
    },
)
async def search(
    request: Request,
    text: Annotated[
        str,
        Query(
            min_length=1,
            max_length=2000,
            description="Произвольный текстовый запрос. Все слова должны встретиться в тексте документа.",
            examples=["конкурс"],
        ),
    ],
) -> list[DocumentOut]:
    query = text.strip()
    if not query:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="text is empty")
    try:
        async with request.app.state.sessionmaker() as session:
            documents = await search_documents(
                session,
                request.app.state.es,
                request.app.state.settings,
                query,
            )
    except MatchWindowExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"query matched {exc.total} documents, above the index fetch window "
                f"of {exc.window}"
            ),
        ) from exc
    except (ElasticsearchConnectionError, ApiError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="search index is unavailable",
        ) from exc
    return [DocumentOut.model_validate(document) for document in documents]


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить документ",
    operation_id="deleteDocument",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Документ с таким id не найден"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Индекс недоступен"},
    },
)
async def remove_document(document_id: int, request: Request) -> Response:
    try:
        async with request.app.state.sessionmaker() as session:
            await delete_document(
                session,
                request.app.state.es,
                request.app.state.settings.es_index,
                document_id,
            )
    except DocumentNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"document {exc.document_id} was not found",
        ) from exc
    except (ElasticsearchConnectionError, ApiError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="search index is unavailable",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
