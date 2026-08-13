"""
Tool executor - executes function calls requested by the LLM.
Uses existing service layer for database operations.
Refactored to use Pydantic schemas for type safety.
"""
import logging
from typing import Any
from sqlmodel import Session
from services.book_service import BookService
from services.loan_service import LoanService
from services.member_service import MemberService
from services.storage import StorageService
from core.exceptions import (
    BookNotFoundException,
    MemberNotFoundException,
    NoAvailableCopiesException,
    BookAlreadyBorrowedException,
    InactiveMemberException,
)
from schemas.tool_responses import (
    SearchBooksResult,
    CheckAvailabilityResult,
    GetMemberLoansResult,
    BookPDFUrlResult,
    CalculateLateFeeResult,
    LateFeeCalculation,
    CreateLoanResult,
    ExtendLoanResult,
    ToolResponse,
)
from schemas.loan import LoanCreate
from datetime import datetime, timezone, timedelta
from models.book import Book
from models.member import Member

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Executes tool calls made by the LLM using existing services."""

    def __init__(self, session: Session, storage: StorageService):
        self.session = session
        self.book_service = BookService(session, storage)
        self.loan_service = LoanService(session)
        self.member_service = MemberService(session)

        # Tool dispatch registry - maps tool names to handler methods
        # This is the SINGLE SOURCE OF TRUTH for available tools
        self._tool_registry = {
            "search_books": self._search_books,
            "check_availability": self._check_availability,
            "get_member_loans": self._get_member_loans,
            "get_book_pdf_url": self._get_book_pdf_url,
            "calculate_late_fees": self._calculate_late_fees,
            "create_loan": self._create_loan,
            "extend_loan": self._extend_loan,
        }
    
    def get_available_tools(self) -> list[str]:
        """Get list of all available tool names from the registry."""
        return list(self._tool_registry.keys())

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """
        Execute a tool and return the result as a JSON string.

        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments for the tool

        Returns:
            JSON string with the result
        """
        try:
            # Get handler from registry
            handler = self._tool_registry.get(tool_name)

            if handler is None:
                error_response = ToolResponse(success=False, error=f"Unknown tool: {tool_name}")
                return error_response.model_dump_json()

            # Execute the handler with arguments
            return handler(**arguments)

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            error_response = ToolResponse(success=False, error=str(e))
            return error_response.model_dump_json()

    def _search_books(self, query: str, filter_by: str) -> str:
        """Search for books by title, author, or genre using BookService."""
        if filter_by not in ["title", "author", "genre"]:
            response = SearchBooksResult(
                success=False,
                error=f"Invalid filter_by: {filter_by}. Must be 'title', 'author', or 'genre'"
            )
            return response.model_dump_json()

        if filter_by == "genre":
            books = self.book_service.list(genre=query, limit=100)
        else:
            books = self.book_service.list(search=query, limit=100)

        results = [
            {
                "id": book.id,
                "title": book.title,
                "author": book.author,
                "genre": book.genre,
                "isbn": book.isbn,
                "total_copies": book.total_copies,
                "available_copies": book.available_copies,
            }
            for book in books
        ]

        message = None if results else f"No books found matching '{query}' in {filter_by}"
        response = SearchBooksResult(
            success=True,
            results=results,
            count=len(results),
            message=message
        )
        return response.model_dump_json()

    def _check_availability(self, book_id: int) -> str:
        """Check availability of a specific book using BookService and LoanService."""
        book = self.book_service.get_by_id(book_id)

        if not book:
            response = CheckAvailabilityResult(
                success=False,
                error=f"Book with ID {book_id} not found"
            )
            return response.model_dump_json()

        response = CheckAvailabilityResult(
            success=True,
            book_id=book.id,
            book_title=book.title,
            total_copies=book.total_copies,
            available_copies=book.available_copies,
            is_available=book.available_copies > 0
        )
        return response.model_dump_json()

    def _get_member_loans(self, member_id: int) -> str:
        """Get all active loans for a member using MemberService and LoanService."""
        try:
            member = self.member_service.get_by_id(member_id)
            loan_responses = self.loan_service.list(member_id=member_id, active_only=True)

            # Convert LoanResponse objects to dicts for JSON serialization
            loan_details = [loan.model_dump() for loan in loan_responses]

            message = "No active loans" if not loan_details else None
            response = GetMemberLoansResult(
                success=True,
                member_id=member.id,
                active_loans=loan_details,
                count=len(loan_details),
                message=message
            )
            return response.model_dump_json()

        except MemberNotFoundException:
            response = GetMemberLoansResult(
                success=False,
                error=f"Member with ID {member_id} not found"
            )
            return response.model_dump_json()

    def _get_book_pdf_url(self, book_id: int) -> str:
        """Get presigned URL for book's PDF file using StorageService."""
        book = self.book_service.get_by_id(book_id)

        if not book:
            response = BookPDFUrlResult(
                success=False,
                error=f"Book with ID {book_id} not found"
            )
            return response.model_dump_json()

        if not book.file_path:
            response = BookPDFUrlResult(
                success=False,
                book_id=book.id,
                book_title=book.title,
                error=f"Book '{book.title}' does not have a PDF file uploaded"
            )
            return response.model_dump_json()

        presigned_url = self.book_service.storage.get_presigned_url(book.file_path)

        response = BookPDFUrlResult(
            success=True,
            book_id=book.id,
            book_title=book.title,
            url=presigned_url,
            expires_in=3600,  # 1 hour
            message=f"Download URL generated for '{book.title}'"
        )
        return response.model_dump_json()

    def _calculate_late_fees(self, member_id: int, fee_per_day: float = 1.0) -> str:
        """Calculate late fees for a member's overdue books."""
        try:
            member = self.member_service.get_by_id(member_id)
            active_loans = self.loan_service.list(member_id=member_id, active_only=True)

            now = datetime.now(timezone.utc).date()
            overdue_details = []
            total_fees = 0.0

            for loan_resp in active_loans:
                if loan_resp.due_date < now:
                    days_overdue = (now - loan_resp.due_date).days
                    fee = days_overdue * fee_per_day
                    total_fees += fee

                    overdue_details.append(
                        LateFeeCalculation(
                            loan_id=loan_resp.id,
                            book_title=loan_resp.book.title if loan_resp.book else "Unknown",
                            days_overdue=days_overdue,
                            fee_amount=round(fee, 2)
                        )
                    )

            message = "No overdue books" if not overdue_details else None
            response = CalculateLateFeeResult(
                success=True,
                member_id=member.id,
                total_fees=round(total_fees, 2),
                overdue_loans=overdue_details,
                fee_per_day=fee_per_day,
                message=message
            )
            return response.model_dump_json()

        except MemberNotFoundException:
            response = CalculateLateFeeResult(
                success=False,
                error=f"Member with ID {member_id} not found"
            )
            return response.model_dump_json()

    def _create_loan(self, book_id: int, member_id: int, loan_days: int = 14) -> str:
        """Create a new loan using LoanService."""
        # Exception to error message mapping
        error_messages = {
            BookNotFoundException: f"Book with ID {book_id} not found",
            MemberNotFoundException: f"Member with ID {member_id} not found",
            NoAvailableCopiesException: "All copies of this book are currently on loan",
            BookAlreadyBorrowedException: "This member already has an active loan for this book",
            InactiveMemberException: "Member account is inactive and cannot borrow books",
        }
        
        try:
            loan_data = LoanCreate(
                book_id=book_id,
                member_id=member_id,
                loan_days=loan_days
            )
            
            loan_response = self.loan_service.borrow(loan_data)

            book_title = loan_response.book.title if loan_response.book else "Unknown"
            response = CreateLoanResult(
                success=True,
                loan_id=loan_response.id,
                book_id=loan_response.book_id,
                book_title=book_title,
                member_id=loan_response.member_id,
                borrowed_at=loan_response.borrowed_at,
                due_date=loan_response.due_date,
                message=f"Successfully borrowed '{book_title}' until {loan_response.due_date.isoformat()}"
            )
            return response.model_dump_json()
            
        except tuple(error_messages.keys()) as e:
            error_msg = error_messages.get(type(e), str(e))
            response = CreateLoanResult(success=False, error=error_msg)
            return response.model_dump_json()

    def _extend_loan(self, loan_id: int, additional_days: int) -> str:
        """Extend the due date of an existing loan."""
        try:
            loan = self.loan_service.get_by_id(loan_id)

            if not loan:
                response = ExtendLoanResult(
                    success=False,
                    error=f"Loan with ID {loan_id} not found"
                )
                return response.model_dump_json()

            if loan.is_returned:
                response = ExtendLoanResult(
                    success=False,
                    loan_id=loan.id,
                    error="Cannot extend a loan that has already been returned"
                )
                return response.model_dump_json()

            # Check if loan is overdue
            now = datetime.now(timezone.utc).date()
            if loan.due_date < now:
                days_overdue = (now - loan.due_date).days
                response = ExtendLoanResult(
                    success=False,
                    loan_id=loan.id,
                    error=f"Cannot extend overdue loan. Book is {days_overdue} days overdue."
                )
                return response.model_dump_json()

            # Validate extension limit
            if additional_days > 14:
                response = ExtendLoanResult(
                    success=False,
                    loan_id=loan.id,
                    error="Maximum extension is 14 days"
                )
                return response.model_dump_json()

            if additional_days < 1:
                response = ExtendLoanResult(
                    success=False,
                    loan_id=loan.id,
                    error="Extension must be at least 1 day"
                )
                return response.model_dump_json()

            # Extend the loan
            old_due_date = loan.due_date
            loan.due_date = loan.due_date + timedelta(days=additional_days)

            self.session.add(loan)
            self.session.commit()
            self.session.refresh(loan)

            # Get book details for response
            book = self.session.get(Book, loan.book_id)

            response = ExtendLoanResult(
                success=True,
                loan_id=loan.id,
                book_title=book.title if book else "Unknown",
                old_due_date=old_due_date,
                new_due_date=loan.due_date,
                days_extended=additional_days,
                message=f"Loan extended by {additional_days} days. New due date: {loan.due_date.isoformat()}"
            )
            return response.model_dump_json()

        except Exception as e:
            response = ExtendLoanResult(
                success=False,
                error=str(e)
            )
            return response.model_dump_json()
