from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, select

from core.config import settings
from core.exceptions import (
    BookAlreadyBorrowedException,
    BookAlreadyReturnedException,
    BookNotFoundException,
    InactiveMemberException,
    LoanNotFoundException,
    LoanPeriodExceededException,
    MemberNotFoundException,
    NoAvailableCopiesException,
)
from models.book import Book
from models.loan import Loan
from models.member import Member
from schemas.loan import LoanCreate, LoanResponse, ReturnResponse


class LoanService:

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, loan_id: int) -> Optional[Loan]:
        return self.session.get(Loan, loan_id)

    def get_by_id_or_raise(self, loan_id: int) -> Loan:
        loan = self.get_by_id(loan_id)
        if not loan:
            raise LoanNotFoundException
        return loan

    def list(
        self,
        member_id: Optional[int] = None,
        book_id: Optional[int] = None,
        active_only: bool = False,
        overdue_only: bool = False,
        offset: int = 0,
        limit: int = 20,
    ) -> list[LoanResponse]:
        query = select(Loan)

        if member_id is not None:
            query = query.where(Loan.member_id == member_id)
        if book_id is not None:
            query = query.where(Loan.book_id == book_id)
        if active_only or overdue_only:
            query = query.where(Loan.is_returned == False)

        loans = list(self.session.exec(query.offset(offset).limit(limit)).all())

        # overdue filter applied in Python — avoids dialect-specific date SQL
        if overdue_only:
            loans = [l for l in loans if l.due_date < date.today()]

        return [LoanResponse.from_loan(l) for l in loans]

    def borrow(self, data: LoanCreate) -> LoanResponse:
        """
        Creates a loan and decrements available_copies atomically.

        Concurrency: SELECT FOR UPDATE locks the book row for the duration
        of this transaction. A second concurrent borrow of the same book
        will block here until the first commits, then re-read available_copies
        and fail correctly if no copies remain.
        """
        loan_days = data.loan_days or settings.DEFAULT_LOAN_DAYS
        if loan_days > settings.MAX_LOAN_DAYS:
            raise LoanPeriodExceededException(
                f"Maximum loan period is {settings.MAX_LOAN_DAYS} days"
            )

        # Lock the book row before any reads to prevent concurrent oversell
        # select * from book where id = {data.book_id} for update
        book = self.session.exec(
            select(Book).where(Book.id == data.book_id).with_for_update()
        ).first()

        if not book:
            raise BookNotFoundException

        member = self.session.get(Member, data.member_id)
        if not member:
            raise MemberNotFoundException
        if not member.is_active:
            raise InactiveMemberException

        if book.available_copies < 1:
            raise NoAvailableCopiesException

        # Check member doesn't already have an active loan for this book
        existing = self.session.exec(
            select(Loan).where(
                Loan.book_id == data.book_id,
                Loan.member_id == data.member_id,
                Loan.is_returned == False,
            )
        ).first()
        if existing:
            raise BookAlreadyBorrowedException

        due_date = date.today() + timedelta(days=loan_days)

        loan = Loan(
            book_id=data.book_id,
            member_id=data.member_id,
            due_date=due_date,
        )
        book.available_copies -= 1

        # Both writes in one transaction — if either fails, both roll back
        self.session.add(loan)
        self.session.add(book)
        self.session.commit()
        self.session.refresh(loan)

        return LoanResponse.from_loan(loan)

    def return_book(self, loan_id: int) -> ReturnResponse:
        """
        Marks a loan returned and increments available_copies atomically.
        """
        loan = self.get_by_id_or_raise(loan_id)

        if loan.is_returned:
            raise BookAlreadyReturnedException

        # Lock the book row before incrementing
        book = self.session.exec(
            select(Book).where(Book.id == loan.book_id).with_for_update()
        ).first()

        if book:
            loan.is_returned = True
            loan.returned_at = datetime.now(timezone.utc)
            book.available_copies += 1

        self.session.add(loan)
        self.session.add(book)
        self.session.commit()
        self.session.refresh(loan)

        return ReturnResponse(
            message="Book returned successfully",
            loan=LoanResponse.from_loan(loan),
        )
