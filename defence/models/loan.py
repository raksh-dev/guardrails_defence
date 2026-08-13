from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Optional
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.book import Book
    from models.member import Member


class Loan(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: int = Field(foreign_key="book.id", index=True)
    member_id: int = Field(foreign_key="member.id", index=True)

    borrowed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    due_date: date
    returned_at: Optional[datetime] = None
    is_returned: bool = Field(default=False)

    book: Optional["Book"] = Relationship(back_populates="loans")
    member: Optional["Member"] = Relationship(back_populates="loans")
