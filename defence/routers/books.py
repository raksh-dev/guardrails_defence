from typing import Optional
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlmodel import Session

from core.file_validator import validate_upload
from database.db import get_session
from schemas.book import BookCreate, BookFileResponse, BookResponse, BookUpdate
from models.book import Book
from services.book_service import BookService
from services.storage import StorageService
from services.supabase_storage import get_storage_service

router = APIRouter(prefix="/books", tags=["Books"])


def get_book_service(
    session: Session = Depends(get_session),
    storage: StorageService = Depends(get_storage_service),
) -> BookService:
    return BookService(session, storage)


@router.post("/", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
def create_book(
    data: BookCreate,
    service: BookService = Depends(get_book_service),
) -> Book:
    return service.create(data)


@router.get("/", response_model=list[BookResponse])
def list_books(
    search: Optional[str] = Query(None, description="Search by title or author"),
    genre: Optional[str] = Query(None),
    available_only: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    service: BookService = Depends(get_book_service),
) -> list[Book]:
    return service.list(
        search=search,
        genre=genre,
        available_only=available_only,
        offset=offset,
        limit=limit,
    )


@router.get("/{book_id}", response_model=BookResponse)
def get_book(
    book_id: int,
    service: BookService = Depends(get_book_service),
) -> BookResponse:
    return service.get_by_id(book_id)


@router.patch("/{book_id}", response_model=BookResponse)
def update_book(
    book_id: int,
    data: BookUpdate,
    service: BookService = Depends(get_book_service),
) -> Book:
    book = service.get_by_id(book_id)
    return service.update(book, data)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(
    book_id: int,
    service: BookService = Depends(get_book_service),
) -> None:
    book = service.get_by_id(book_id)
    service.delete(book)


@router.post("/{book_id}/file", response_model=BookResponse, summary="Upload the book's file")
async def upload_file(
    book_id: int,
    file: UploadFile = File(..., description="Book file"),
    service: BookService = Depends(get_book_service),
) -> BookResponse:
    file_bytes, extension, content_type = await validate_upload(file)
    return service.upload_file(book_id, file_bytes, extension, content_type)


@router.get("/{book_id}/file/download", response_model=BookFileResponse, summary="Get a presigned download URL for the book's file")
def get_download_url(
    book_id: int,
    service: BookService = Depends(get_book_service),
) -> BookFileResponse:
    return service.get_download_url(book_id)


@router.delete("/{book_id}/file", response_model=BookResponse, summary="Remove the book's file from storage")
def delete_file(
    book_id: int,
    service: BookService = Depends(get_book_service),
) -> BookResponse:
    return service.delete_file(book_id)