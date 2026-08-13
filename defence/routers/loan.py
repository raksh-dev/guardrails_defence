from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from database.db import get_session
from schemas.loan import LoanResponse, LoanCreate, ReturnResponse
from services.loan_service import LoanService

router = APIRouter(prefix="/loans", tags=["Loans"])


def get_service(session: Session = Depends(get_session)) -> LoanService:
    return LoanService(session)


@router.post(
    "/",
    response_model=LoanResponse,
    status_code=status.HTTP_201_CREATED,
)
def borrow_book(
    data: LoanCreate,
    service: LoanService = Depends(get_service),
) -> LoanResponse:
    return service.borrow(data)


@router.post(
    "/{loan_id}/return",
    response_model=ReturnResponse,
)
def return_book(
    loan_id: int,
    service: LoanService = Depends(get_service),
) -> ReturnResponse:
    return service.return_book(loan_id)


@router.get(
    "/",
    response_model=list[LoanResponse],
)
def list_loans(
    service: LoanService = Depends(get_service),
    member_id: Optional[int] = Query(None),
    book_id: Optional[int] = Query(None),
    active_only: bool = Query(False),
    overdue_only: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> list[LoanResponse]:
    return service.list(
        member_id=member_id,
        book_id=book_id,
        active_only=active_only,
        overdue_only=overdue_only,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{loan_id}",
    response_model=LoanResponse,
)
def get_loan(
    loan_id: int,
    service: LoanService = Depends(get_service),
) -> LoanResponse:
    loan = service.get_by_id_or_raise(loan_id)
    return LoanResponse.from_loan(loan)