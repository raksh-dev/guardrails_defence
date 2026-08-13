from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator

class BookCreate(BaseModel):
    title: str
    author: str
    isbn: str
    genre: Optional[str] = None
    published_year: Optional[int] = None
    total_copies: int = 1

    @field_validator("title", "author", "isbn", mode="before")
    @classmethod
    def must_not_be_empty(cls, v, info):
        if v is None or str(v).strip() == "":
            raise ValueError(f"{info.field_name} must not be empty")
        return str(v).strip()
 
    @field_validator("published_year")
    @classmethod
    def valid_published_year(cls, v):
        from datetime import date
        if v < 1:
            raise ValueError("published_year must be a positive number")
        if v > date.today().year:
            raise ValueError("published_year cannot be in the future")
        return v
 
    @field_validator("total_copies")
    @classmethod
    def copies_must_be_positive(cls, v):
        if v < 1:
            raise ValueError("total_copies must be at least 1")
        return v


class BookUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    genre: Optional[str] = None
    published_year: Optional[int] = None
    total_copies: Optional[int] = None


class BookResponse(BaseModel):
    id: int
    title: str
    author: str
    isbn: str
    genre: Optional[str]
    published_year: Optional[int]
    total_copies: int
    available_copies: int
    created_at: datetime
    file_path: Optional[str]

    model_config = {"from_attributes": True}

class BookFileResponse(BaseModel):
    """Returned when requesting a download URL for a book's file."""
    book_id: int
    filename: str
    download_url: str               # presigned URL
    expires_in_seconds: int