from typing import Optional
from sqlmodel import Session, select, func

from core.exceptions import (
    DuplicateEmailException,
    InactiveMemberException,
    MemberDeactivatedException,
    MemberNotFoundException,
)
from models.loan import Loan
from models.member import Member
from schemas.member import MemberCreate, MemberUpdate


class MemberService:

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, member_id: int) -> Member:
        member = self.session.get(Member, member_id)
        if not member:
            raise MemberNotFoundException
        return member

    def get_by_email(self, email: str) -> Optional[Member]:
        return self.session.exec(
            select(Member).where(Member.email == email)
        ).first()

    def list(
        self,
        search: Optional[str] = None,
        active_only: bool = True,
        offset: int = 0,
        limit: int = 20,
    ) -> list[Member]:
        query = select(Member)
        if search:
            term = f"%{search.lower()}%"
            query = query.where(
                func.lower(Member.name).like(term)
                | func.lower(Member.email).like(term)
            )
        if active_only:
            query = query.where(Member.is_active == True)
        return list(self.session.exec(query.offset(offset).limit(limit)).all())

    def get_active_loan_count(self, member_id: int) -> int:
        result = self.session.exec(
            select(func.count()).where(
                Loan.member_id == member_id,
                Loan.is_returned == False,
            )
        )
        return result.one()

    def create(self, data: MemberCreate) -> Member:
        if self.get_by_email(data.email):
            raise DuplicateEmailException(
                f"A member with email '{data.email}' already exists"
            )
        member = Member(**data.model_dump())
        self.session.add(member)
        self.session.commit()
        self.session.refresh(member)
        return member

    def update(self, member_id: int, data: MemberUpdate) -> Member:
        member = self.get_by_id(member_id)

        if data.email and data.email != member.email:
            if self.get_by_email(data.email):
                raise DuplicateEmailException(
                    f"A member with email '{data.email}' already exists"
                )

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(member, field, value)

        self.session.add(member)
        self.session.commit()
        self.session.refresh(member)
        return member

    def deactivate(self, member_id: int) -> None:
        """
        Soft delete
        """
        member = self.get_by_id(member_id)
        if not member.is_active:
            raise InactiveMemberException("Member is already inactive")
        if self.get_active_loan_count(member_id) > 0:
            raise MemberDeactivatedException(
                "Cannot deactivate a member who has active loans"
            )
        member.is_active = False
        self.session.add(member)
        self.session.commit()
