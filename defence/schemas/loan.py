from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel

from schemas.book import BookResponse
from schemas.member import MemberResponse


class LoanCreate(BaseModel):
    book_id: int
    member_id: int
    loan_days: Optional[int] = None  # if None, defaults to settings.DEFAULT_LOAN_DAYS


class LoanResponse(BaseModel):
    id: int
    book_id: int
    member_id: int
    borrowed_at: datetime
    due_date: date
    returned_at: Optional[datetime]
    is_returned: bool
    is_overdue: bool

    book: Optional[BookResponse] = None
    member: Optional[MemberResponse] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_loan(cls, loan) -> "LoanResponse":
        due = loan.due_date.date() if isinstance(loan.due_date, datetime) else loan.due_date
        return cls(
            id=loan.id,
            book_id=loan.book_id,
            member_id=loan.member_id,
            borrowed_at=loan.borrowed_at,
            due_date=loan.due_date,
            returned_at=loan.returned_at,
            is_returned=loan.is_returned,
            is_overdue=not loan.is_returned and due < date.today(),
            book=loan.book,
            member=loan.member,
        )


class ReturnResponse(BaseModel):
    message: str
    loan: LoanResponse