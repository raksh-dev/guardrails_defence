from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator


class MemberCreate(BaseModel):
    name: str
    email: EmailStr

    @field_validator("name", mode="before")
    @classmethod
    def name_not_empty(cls, v):
        if not v or str(v).strip() == "":
            raise ValueError("name must not be empty")
        return str(v).strip()


class MemberUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None

    @field_validator("name", mode="before")
    @classmethod
    def name_not_empty(cls, v):
        if v is not None and str(v).strip() == "":
            raise ValueError("name must not be empty")
        return str(v).strip() if v else v


class MemberResponse(BaseModel):
    id: int
    name: str
    email: str
    membership_date: date
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}