"""Documents router: upload, list, get, delete PDFs (MongoDB)."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.models.schemas import DocumentChunkOut, DocumentOut
from app.services.document_service import (
    DocumentIngestionError,
    DocumentService,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("", response_model=DocumentOut)
async def upload_document(
    client_id: str = Form(...),
    file: UploadFile = File(...),
) -> DocumentOut:

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="only PDF files are supported",
        )

    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="empty file",
        )

    try:

        service = DocumentService()

        doc = service.ingest(
            client_id,
            file.filename,
            content,
        )

    except DocumentIngestionError as exc:

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return DocumentOut(
        id=doc["id"],
        client_id=doc["client_id"],
        filename=doc["filename"],
        mime_type=doc["mime_type"],
        size_bytes=doc["size_bytes"],
        page_count=doc["page_count"],
        status=doc["status"],
        section_index=doc.get("section_index") or [],
        created_at=doc["created_at"],
    )


@router.get("", response_model=list[DocumentOut])
def list_documents(client_id: str):
    print("========== LIST DOCUMENTS ==========")
    print("CLIENT:", client_id)

    try:
        service = DocumentService()
        rows = service.list_documents(client_id)

        print("ROWS:", rows)

        return [
            DocumentOut(
                id=row["id"],
                client_id=row["client_id"],
                filename=row["filename"],
                mime_type=row["mime_type"],
                size_bytes=row["size_bytes"],
                page_count=row["page_count"],
                status=row["status"],
                section_index=row.get("section_index") or [],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str) -> DocumentOut:

    try:

        row = DocumentService().get_document(document_id)

    except DocumentIngestionError as exc:

        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    return DocumentOut(
        id=row["id"],
        client_id=row["client_id"],
        filename=row["filename"],
        mime_type=row["mime_type"],
        size_bytes=row["size_bytes"],
        page_count=row["page_count"],
        status=row["status"],
        section_index=row.get("section_index") or [],
        created_at=row["created_at"],
    )


@router.delete("/{document_id}")
def delete_document(document_id: str):

    DocumentService().delete_document(document_id)

    return {
        "status": "deleted"
    }


@router.get(
    "/{document_id}/chunks",
    response_model=list[DocumentChunkOut],
)
def list_chunks(document_id: str):

    rows = DocumentService().list_chunks(document_id)

    return [
        DocumentChunkOut(
            id=row["id"],
            document_id=row["document_id"],
            chunk_index=row["chunk_index"],
            page_number=row["page_number"],
            section=row.get("section"),
            content=row["content"],
            token_count=row["token_count"],
        )
        for row in rows
    ]