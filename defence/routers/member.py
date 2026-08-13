from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from database.db import get_session
from schemas.member import MemberCreate, MemberResponse, MemberUpdate
from services.member_service import MemberService
from models.member import Member

router = APIRouter(prefix="/members", tags=["Members"])


def get_service(session: Session = Depends(get_session)) -> MemberService:
    return MemberService(session)


@router.post(
    "/",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_member(
    data: MemberCreate,
    service: MemberService = Depends(get_service),
) -> Member:
    return service.create(data)


@router.get(
    "/",
    response_model=list[MemberResponse],
)
def list_members(
    service: MemberService = Depends(get_service),
    search: Optional[str] = Query(None, description="Search by name or email"),
    active_only: bool = Query(True),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> list[Member]:
    return service.list(
        search=search,
        active_only=active_only,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{member_id}",
    response_model=MemberResponse,
)
def get_member(
    member_id: int,
    service: MemberService = Depends(get_service),
) -> Member:
    return service.get_by_id(member_id)


@router.patch(
    "/{member_id}",
    response_model=MemberResponse,
)
def update_member(
    member_id: int,
    data: MemberUpdate,
    service: MemberService = Depends(get_service),
) -> Member:
    return service.update(member_id, data)


@router.delete(
    "/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def deactivate_member(
    member_id: int,
    service: MemberService = Depends(get_service),
) -> None:
    service.deactivate(member_id)