"""
Tool definitions for LLM function calling.
Defines the schema for tools that the LLM can invoke.
"""

LIBRARY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_books",
            "description": "Search for books in the library by title, author, or genre. Returns a list of matching books with their details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g., 'Python programming', 'Agatha Christie', 'Science Fiction')",
                    },
                    "filter_by": {
                        "type": "string",
                        "enum": ["title", "author", "genre"],
                        "description": "Which field to search in: 'title', 'author', or 'genre'",
                    },
                },
                "required": ["query", "filter_by"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Check the availability status of a specific book. Returns total copies, available copies, and current loan status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "The unique ID of the book to check",
                    },
                },
                "required": ["book_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_member_loans",
            "description": "Get all active loans for a specific library member. Returns a list of books currently borrowed, due dates, and any overdue status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_id": {
                        "type": "integer",
                        "description": "The unique ID of the library member",
                    },
                },
                "required": ["member_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_book_pdf_url",
            "description": "Get a presigned download URL for a book's PDF file. Returns a time-limited URL that can be used to download the book.",
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "The unique ID of the book",
                    },
                },
                "required": ["book_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_late_fees",
            "description": "Calculate late fees for a member's overdue books. Returns total fees, breakdown by book, and days overdue for each loan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_id": {
                        "type": "integer",
                        "description": "The unique ID of the library member",
                    },
                    "fee_per_day": {
                        "type": "number",
                        "description": "Fee charged per day (default: 1.0)",
                        "default": 1.0,
                    },
                },
                "required": ["member_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_loan",
            "description": "Create a new loan (borrow a book) for a member. Validates book availability and member eligibility before creating the loan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "The unique ID of the book to borrow",
                    },
                    "member_id": {
                        "type": "integer",
                        "description": "The unique ID of the member borrowing the book",
                    },
                    "loan_days": {
                        "type": "integer",
                        "description": "Number of days for the loan (default: 14, max: 30)",
                        "default": 14,
                    },
                },
                "required": ["book_id", "member_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extend_loan",
            "description": "Extend the due date of an existing loan. Can only extend non-overdue loans.",
            "parameters": {
                "type": "object",
                "properties": {
                    "loan_id": {
                        "type": "integer",
                        "description": "The unique ID of the loan to extend",
                    },
                    "additional_days": {
                        "type": "integer",
                        "description": "Number of additional days to extend (max: 14)",
                    },
                },
                "required": ["loan_id", "additional_days"],
            },
        },
    },
]


def get_available_tool_names() -> list[str]:
    """
    Get list of all available tool names.
    Useful for validation and documentation.
    """
    return [tool["function"]["name"] for tool in LIBRARY_TOOLS]


def validate_tool_definitions(executor_tools: list[str]) -> None:
    """
    Validate that tool definitions match executor registry.
    Raises ValueError if there's a mismatch.
    
    Args:
        executor_tools: List of tool names from ToolExecutor registry
    """
    definition_tools = set(get_available_tool_names())
    executor_tool_set = set(executor_tools)
    
    missing_in_definitions = executor_tool_set - definition_tools
    missing_in_executor = definition_tools - executor_tool_set
    
    errors = []
    if missing_in_definitions:
        errors.append(f"Tools in executor but missing definitions: {missing_in_definitions}")
    if missing_in_executor:
        errors.append(f"Tools in definitions but missing in executor: {missing_in_executor}")
    
    if errors:
        raise ValueError("Tool definition mismatch:\n" + "\n".join(errors))


# Available tools for easy reference
AVAILABLE_TOOLS = get_available_tool_names()
