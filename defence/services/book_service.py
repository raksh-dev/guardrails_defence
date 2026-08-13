import uuid

from typing import Optional
from sqlmodel import Session, select, func

from core.config import settings

from schemas.book import BookCreate, BookFileResponse, BookResponse, BookUpdate
from models.book import Book

from core.exceptions import DuplicateISBNException, BookNotFoundException, BookFileNotFoundException
from core.cache import book_cache, cached

from services.storage import StorageService

class BookService:
    def __init__(self, session: Session, storage: StorageService):
        self.session = session
        self.storage = storage

    @cached(cache=book_cache, key_arg="book_id")
    def get_by_id(self, book_id: int) -> Optional[Book]:
        return self.session.get(Book, book_id)

    def get_by_isbn(self, isbn: str) -> Optional[Book]:
        return self.session.exec(
            select(Book).where(Book.isbn == isbn)
        ).first()

    def list(
        self,
        search: Optional[str] = None,
        genre: Optional[str] = None,
        available_only: bool = False,
        offset: int = 0,
        limit: int = 20,
    ) -> list[Book]:
        query = select(Book)

        if search:
            term = f"%{search.lower()}%"
            query = query.where(
                func.lower(Book.title).like(term)
                | func.lower(Book.author).like(term)
            )
        if genre:
            query = query.where(
                func.lower(Book.genre).like(f"%{genre.lower()}%")
            )
        if available_only:
            query = query.where(Book.available_copies > 0)

        return list(self.session.exec(query.offset(offset).limit(limit)).all())

    def create(self, data: BookCreate) -> Book:
        if self.get_by_isbn(data.isbn):
            raise DuplicateISBNException()

        book = Book(
            **data.model_dump(),
            available_copies=data.total_copies,
        )
        self.session.add(book)
        self.session.commit()
        self.session.refresh(book)
        return book

    def update(self, book: Book, data: BookUpdate) -> Book:
        changes = data.model_dump(exclude_unset=True)

        for field, value in changes.items():
            setattr(book, field, value)

        self.session.add(book)
        self.session.commit()
        self.session.refresh(book)
        
        book_cache.delete(book.id)
        return book

    def delete(self, book: Book) -> None:
        self.session.delete(book)
        self.session.commit()
        
        book_cache.delete(book.id)


    def upload_file(
        self,
        book_id: int,
        file_bytes: bytes,
        extension: str,
        content_type: str,
    ) -> BookResponse:
        book = self.get_by_id(book_id)
        if not book:
            raise BookNotFoundException

        # remove file (if exist) before uploading
        if book.file_path:
            self.storage.delete(book.file_path)

        # Collision Prevention
        storage_path = f"{book_id}/{uuid.uuid4()}.{extension}"
        self.storage.upload(storage_path, file_bytes, content_type)

        book.file_path = storage_path
        self.session.add(book)
        self.session.commit()
        self.session.refresh(book)

        # Cache Invalidation
        book_cache.delete(book_id)
        return BookResponse.model_validate(book)

    def get_download_url(self, book_id: int) -> BookFileResponse:
        book = self.get_by_id(book_id)
        if not book:
            raise BookNotFoundException
        if not book.file_path:
            raise BookFileNotFoundException(
                f"Book '{book.title}' has no file uploaded yet"
            )

        url = self.storage.get_presigned_url(book.file_path)
        filename = book.file_path.rsplit("/", 1)[-1]

        return BookFileResponse(
            book_id=book_id,
            filename=filename,
            download_url=url,
            expires_in_seconds=settings.STORAGE_PRESIGNED_URL_EXPIRY,
        )

    def delete_file(self, book_id: int) -> BookResponse:
        book = self.get_by_id(book_id)
        if not book:
            raise BookNotFoundException
        if not book.file_path:
            raise BookFileNotFoundException(
                f"Book '{book.title}' has no file to delete"
            )

        self.storage.delete(book.file_path)
        book.file_path = None
        self.session.add(book)
        self.session.commit()
        self.session.refresh(book)
        book_cache.delete(book_id)
        return BookResponse.model_validate(book)
