"""
Pydantic schemas for tool execution responses.
Provides type-safe responses instead of raw JSON strings.
"""
from typing import Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ToolResponse(BaseModel):
    """Base response for all tool executions."""
    success: bool
    error: Optional[str] = None
    message: Optional[str] = None


class SearchBooksResult(ToolResponse):
    """Response for search_books tool."""
    results: list[dict] = Field(default_factory=list)
    count: int = 0


class BookPDFUrlResult(ToolResponse):
    """Response for get_book_pdf_url tool."""
    book_id: Optional[int] = None
    book_title: Optional[str] = None
    url: Optional[str] = None
    expires_in: Optional[int] = None  # seconds


class LateFeeCalculation(BaseModel):
    """Individual loan fee calculation."""
    loan_id: int
    book_title: str
    days_overdue: int
    fee_amount: float


class CalculateLateFeeResult(ToolResponse):
    """Response for calculate_late_fees tool."""
    member_id: Optional[int] = None
    total_fees: float = 0.0
    overdue_loans: list[LateFeeCalculation] = Field(default_factory=list)
    fee_per_day: float = 1.0


class CreateLoanResult(ToolResponse):
    """Response for create_loan tool."""
    loan_id: Optional[int] = None
    book_id: Optional[int] = None
    book_title: Optional[str] = None
    member_id: Optional[int] = None
    borrowed_at: Optional[datetime] = None
    due_date: Optional[datetime] = None


class ExtendLoanResult(ToolResponse):
    """Response for extend_loan tool."""
    loan_id: Optional[int] = None
    book_title: Optional[str] = None
    old_due_date: Optional[datetime] = None
    new_due_date: Optional[datetime] = None
    days_extended: Optional[int] = None


class CheckAvailabilityResult(ToolResponse):
    """Response for check_availability tool."""
    book_id: Optional[int] = None
    book_title: Optional[str] = None
    total_copies: int = 0
    available_copies: int = 0
    is_available: bool = False


class GetMemberLoansResult(ToolResponse):
    """Response for get_member_loans tool."""
    member_id: Optional[int] = None
    active_loans: list[dict] = Field(default_factory=list)
    count: int = 0
