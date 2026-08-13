# Library Management API - Complete Documentation

## Table of Contents
1. [Project Overview](#project-overview)
2. [FastAPI Fundamentals](#fastapi-fundamentals)
3. [Project Architecture](#project-architecture)
4. [Setup & Installation](#setup--installation)
5. [API Reference](#api-reference)
6. [Custom Exceptions](#custom-exceptions)
7. [Code Examples](#code-examples)
8. [Development Guide](#development-guide)

---

## Project Overview

**Library Management API** is a production-ready REST API built with **FastAPI** that manages a library system. It allows users to create, retrieve, update, and delete books with features like advanced filtering, inventory management, and custom exception handling.

### Key Features
- Complete CRUD operations for books
- Advanced search and filtering (by title, author, genre)
- Inventory tracking (total copies vs available copies)
- Custom exception handling with semantic HTTP status codes
- Data validation using Pydantic v2
- PostgreSQL/SQLite database support via SQLModel
- Automatic interactive API documentation
- Middleware for request logging

### Tech Stack
| Component         | Technology                       |
| ----------------- | -------------------------------- |
| Framework         | FastAPI                          |
| Web Server        | Uvicorn                          |
| ORM               | SQLModel (SQLAlchemy + Pydantic) |
| Database          | PostgreSQL with Supabase         |
| Validation        | Pydantic v2                      |
| Config Management | Pydantic Settings                |

---

## FastAPI Fundamentals

### What is FastAPI?

FastAPI is a modern Python web framework that makes it easy to build APIs with:
- **Type hints** for automatic validation and documentation
- **Fast performance** 
- **Automatic documentation** (Swagger UI and ReDoc)
- **Data validation** via Pydantic
- **Security features** built-in
- **Dependency injection** system

### Core Concepts

#### 1. **Creating a FastAPI Application**

```python
from fastapi import FastAPI

app = FastAPI(
    title="Library Management System",
    description="A REST API for managing a library",
    version="1.1.0"
)
```

#### 2. **Defining Routes (Endpoints)**

Routes are decorated functions that handle HTTP requests:

```python
from fastapi import APIRouter

router = APIRouter(prefix="/books")

@router.get("/")                    # HTTP method & path
def list_books():                   # Handler function
    return {"books": []}            # Automatic JSON response
```

**HTTP Methods:**
- `GET` - Retrieve data
- `POST` - Create new data
- `PATCH` / `PUT` - Update data
- `DELETE` - Remove data

#### 3. **Path Parameters**

Variables extracted from the URL path:

```python
@router.get("/{book_id}")           # {book_id} is a path parameter
def get_book(book_id: int):
    return {"book_id": book_id}
```

When called: `/books/5` → `book_id = 5`

#### 4. **Query Parameters**

Optional parameters passed in the query string:

```python
from fastapi import Query

@router.get("/")
def list_books(
    search: Optional[str] = Query(None, description="Search by title"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100)
):
    # /books/?search=fiction&offset=0&limit=10
    return {}
```

#### 5. **Request Body (Request Models)**

Using Pydantic models to define request structure:

```python
from pydantic import BaseModel

class BookCreate(BaseModel):
    title: str              # Required field
    author: str
    isbn: str
    genre: Optional[str] = None  # Optional field

@router.post("/")
def create_book(data: BookCreate):
    # Automatic validation & JSON parsing
    return {"created": data.title}
```

**Example request:**
```json
POST /books/
{
    "title": "The Great Gatsby",
    "author": "F. Scott Fitzgerald",
    "isbn": "978-0743273565",
    "genre": "Fiction"
}
```

#### 6. **Response Models**

Define response schema for documentation and validation:

```python
class BookResponse(BaseModel):
    id: int
    title: str
    author: str
    model_config = {"from_attributes": True}  # ORM compatibility

@router.get("/{book_id}", response_model=BookResponse)
def get_book(book_id: int):
    return book_from_database  # Validated against schema
```

#### 7. **Status Codes**

Specify HTTP status codes for responses:

```python
from fastapi import status

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_book(data: BookCreate):
    return book
```

Common status codes:
- `200 OK` - Successful GET/PATCH
- `201 Created` - Successful POST
- `204 No Content` - Successful DELETE
- `400 Bad Request` - Invalid input
- `404 Not Found` - Resource not found
- `409 Conflict` - Resource already exists

#### 8. **Dependency Injection**

```python
def get_session():
    with Session(engine) as session:
        yield session

def get_book_service(session: Session = Depends(get_session)) -> BookService:
    return BookService(session)

class BookService:
    def __init__(self, session: Session):
        self.session = session
    def get_by_id(self, book_id: int) -> Optional[Book]:
        return self.session.get(Book, book_id)
```

A route handler has one job: handle an HTTP request and return a response. It should not be responsible for building the things it needs. DI separates "using a thing" from "constructing a thing." The handler only expresses what it needs, not how to build it. FastAPI figures out the rest.

Tight coupling that compounds as the application gets bigger. Once one handler builds its own dependencies, others copy the pattern. Eventually every handler has 10 lines of setup before any actual work. Adding a new requirement means touching every handler instead of one dependency function.

1. Session lifecycle is managed correctly. The get_session dependency uses a with block, which guarantees the session is closed after the request finishes, even if an exception is raised mid-request. If you manually built sessions inside handlers, you'd need try/finally everywhere and you'd inevitably miss one. Without the yield-based dependency managing the session lifecycle, sessions don't get closed reliably under exceptions. Under load this exhausts the connection pool and the app starts timing out.
2.  Testing becomes straightforward. You can override any dependency for tests without touching production code. FastAPI has a built-in dependency_overrides mechanism:
3.  Cross-cutting concerns attach cleanly. Auth, rate limiting, permissions -> these are things every endpoint needs but none should implement individually. With DI you write it once.

#### 9. **Exception Handling**

FastAPI's exception handling system:

```python
from fastapi import HTTPException, status

@router.get("/{book_id}")
def get_book(book_id: int):
    book = find_book(book_id)
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    return book
```

#### 11. **Middleware**

Functions that process all requests/responses:

```python
@app.middleware("http")
async def log_requests(request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    print(f"Request took {duration}s")
    return response
```

#### 12. **Lifespan Events**

Run code on app startup/shutdown:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("App starting...")
    yield
    # Shutdown
    print("App shutting down...")

app = FastAPI(lifespan=lifespan)
```

#### 13. **Pydantic Validators**

Validate field values in models:

```python
from pydantic import BaseModel, field_validator
from datetime import date

class BookCreate(BaseModel):
    title: str
    published_year: int
    
    @field_validator("published_year")
    @classmethod
    def valid_year(cls, v):
        if v > date.today().year:
            raise ValueError("Year cannot be in the future")
        return v
```

#### 14. **CORS Middleware**

Allow cross-origin requests:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # All origins
    allow_methods=["*"],           # All methods
    allow_headers=["*"],           # All headers
)
```

---

## Project Architecture

### Directory Structure
## Project Architecture

### Directory Structure

```
books_enh/
├── main.py                  # Application entry point
├── requirements.txt         # Package dependencies
├── .env                     # Environment variables
├── core/
│   ├── config.py           # Configuration management
│   └── exceptions.py       # Custom exception classes
├── database/
│   └── db.py               # Database engine & session
├── models/
│   └── models.py           # SQLModel ORM definitions
├── schemas/
│   └── schemas.py          # Pydantic request/response models
├── services/
│   └── book_service.py     # Business logic layer
└── routers/
    └── books.py            # API endpoints
```

### Architecture Layers

```
┌─────────────────────────────────────────────────┐
│         HTTP Requests (Clients)                 │
└──────────────────┬──────────────────────────────┘
                   │
     ┌─────────────▼──────────────┐
     │    Routers (books.py)      │
     │  - Route handlers          │
     │  - Request validation      │
     │  - Exception catching      │
     └──────────────┬─────────────┘
                   │
     ┌─────────────▼──────────────┐
     │   Services (book_service)  │
     │  - Business logic          │
     │  - Data operations         │
     │  - Custom exceptions       │
     └──────────────┬─────────────┘
                   │
     ┌─────────────▼──────────────┐
     │    Models (ORM Layer)      │
     │  - Database tables         │
     │  - Relationships           │
     └──────────────┬─────────────┘
                   │
     ┌─────────────▼──────────────┐
     │   Database (SQLModel)      │
     │  - SQL queries             │
     │  - Transactions            │
     └────────────────────────────┘
```

### Data Flow Example

**Request: Create a book**

```
Client POST /books/ {title: "...", ...}
    ↓
Router: parse & validate with BookCreate schema
    ↓
ServiceMethod: check if ISBN exists
    ↓
If exists → raise BookAlreadyExistsException
    ↓
Exception Handler: catch and return 409 Conflict
    ↓
Response: {detail: "ISBN already exists"}
```

---

## Setup & Installation

### Prerequisites
- Python 3.8+
- pip or uv package manager

### Installation Steps

1. **Create virtual environment:**
```bash
python -m venv venv
source venv/bin/activate          # Linux/Mac
# or
venv\Scripts\activate             # Windows
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Environment configuration:**
```bash
# Edit .env with your database credentials
# DATABASE_URL=postgresql://user:password@localhost/dbname
```

4. **Run the server:**
```bash
uvicorn main:app --reload
```

5. **Access API docs:**
- Swagger UI: http://localhost:8000/docs
- OpenAPI Schema: http://localhost:8000/openapi.json

---

## API Reference

### Books Endpoints

#### 1. Create a Book
```http
POST /books/
Content-Type: application/json

{
    "title": "The Great Gatsby",
    "author": "F. Scott Fitzgerald",
    "isbn": "978-0743273565",
    "genre": "Fiction",
    "published_year": 1925,
    "total_copies": 5
}
```

**Responses:**
- `201 Created` - Book created successfully
- `409 Conflict` - ISBN already exists
- `422 Unprocessable Entity` - Invalid input

---

#### 2. List Books
```http
GET /books/?search=gatsby&genre=fiction&available_only=true&offset=0&limit=20
```

**Query Parameters:**
| Parameter        | Type               | Description                              |
| ---------------- | ------------------ | ---------------------------------------- |
| `search`         | string (optional)  | Search by title or author                |
| `genre`          | string (optional)  | Filter by genre                          |
| `available_only` | boolean (optional) | Only books with copies available         |
| `offset`         | integer            | Pagination offset (default: 0)           |
| `limit`          | integer            | Results per page (default: 20, max: 100) |

**Response:**
```json
[
    {
        "id": 1,
        "title": "The Great Gatsby",
        "author": "F. Scott Fitzgerald",
        "isbn": "978-0743273565",
        "genre": "Fiction",
        "published_year": 1925,
        "total_copies": 5,
        "available_copies": 3,
        "created_at": "2024-04-05T10:30:00Z"
    }
]
```

---

#### 3. Get Book by ID
```http
GET /books/1
```

**Responses:**
- `200 OK` - Returns book
- `404 Not Found` - Book doesn't exist

---

#### 4. Update Book
```http
PATCH /books/1
Content-Type: application/json

{
    "title": "Updated Title",
    "total_copies": 10
}
```

**Notes:**
- All fields are optional
- When `total_copies` is updated, `available_copies` is adjusted proportionally
- Cannot reduce `total_copies` below copies currently on loan

**Responses:**
- `200 OK` - Book updated
- `404 Not Found` - Book doesn't exist
- `400 Bad Request` - Invalid update

---

#### 5. Delete Book
```http
DELETE /books/1
```

**Constraints:**
- Can only delete if all copies are available (none on loan)
- Returns `204 No Content` on success

**Responses:**
- `204 No Content` - Book deleted
- `404 Not Found` - Book doesn't exist
- `400 Bad Request` - Cannot delete (copies on loan)

---

## Custom Exceptions

The project includes a custom exception hierarchy for semantic error handling:

### Exception Classes

**File:** `core/exceptions.py`

```python
class LibraryException(Exception):
    """Base class for all library exceptions"""
```

### How Custom Exceptions are Used

**In Services (business logic):**
```python
def create(self, data: BookCreate) -> Book:
    if self.get_by_isbn(data.isbn):
        raise BookAlreadyExistsException(data.isbn)
    # ... create book
```

**In Routers (HTTP layer):**
```python
def _get_book(book_id: int, service: BookService) -> Book:
    book = service.get_by_id(book_id)
    if not book:
        raise BookNotFoundException(book_id)
    return book
```


### Benefits of Custom Exceptions
Semantic error handling - Each exception type has specific meaning
Centralized error mapping - Exception handlers in one place
Type safety - Catch specific exceptions, not generic ones
Better debugging - Clear exception names and messages

---

## Code Examples

### Example 1: Creating a Book with Validation

**Request:**
```bash
curl -X POST http://localhost:8000/books/ \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Clean Code",
    "author": "Robert C. Martin",
    "isbn": "0132350882",
    "genre": "Programming",
    "published_year": 2008,
    "total_copies": 3
  }'
```

**Response (201 Created):**
```json
{
    "id": 1,
    "title": "Clean Code",
    "author": "Robert C. Martin",
    "isbn": "0132350882",
    "genre": "Programming",
    "published_year": 2008,
    "total_copies": 3,
    "available_copies": 3,
    "created_at": "2024-04-05T10:30:00Z"
}
```

### Example 2: Duplicate ISBN Error

**Request:**
```bash
curl -X POST http://localhost:8000/books/ \
  -d '{"title": "...", "isbn": "0132350882", ...}'
```

**Response (409 Conflict):**
```json
{
    "detail": "A book with ISBN '0132350882' already exists"
}
```

### Example 3: Advanced Search

**Request:**
```bash
curl "http://localhost:8000/books/?search=python&genre=programming&available_only=true&limit=10"
```

**Response:**
```json
[
    {
        "id": 2,
        "title": "Python Crash Course",
        "author": "Eric Matthes",
        "isbn": "978-1593275",
        "genre": "programming",
        "published_year": 2015,
        "total_copies": 5,
        "available_copies": 2,
        "created_at": "2024-04-05T11:00:00Z"
    }
]
```

---

## Development Guide

### Adding a New Endpoint

**Step 1: Add to schema (schemas.py)**
```python
class AuthorCreate(BaseModel):
    name: str
    birth_year: Optional[int] = None
```

**Step 2: Add service method (author_service.py)**
```python
class AuthorService:
    def create(self, data: AuthorCreate) -> Author:
        # Business logic
        pass
```

**Step 3: Add router (authors.py)**
```python
@router.post("/", response_model=AuthorResponse, status_code=201)
def create_author(data: AuthorCreate, service: AuthorService = Depends(get_author_service)):
    return service.create(data)
```

**Step 4: Include router in main.py**
```python
app.include_router(authors.router)
```

### Adding a New Exception

**Step 1: Define in core/exceptions.py**
```python
class AuthorAlreadyExistsException(LibraryException):
    def __init__(self, name: str):
        super().__init__(f"Author '{name}' already exists")
```

**Step 2: Raise in service**
```python
if self.get_by_name(data.name):
    raise AuthorAlreadyExistsException(data.name)
```

**Step 3: Add handler in main.py**
```python
@app.exception_handler(AuthorAlreadyExistsException)
async def author_exists_handler(request, exc):
    return JSONResponse(
        status_code=409,
        content={"detail": exc.message}
    )
```

### Testing an Endpoint

Using `curl`:
```bash
# Test POST
curl -X POST http://localhost:8000/books/ \
  -H "Content-Type: application/json" \
  -d '{"title": "Test", "author": "Author", "isbn": "123"}'

# Test GET
curl http://localhost:8000/books/

# Test PATCH
curl -X PATCH http://localhost:8000/books/1 \
  -H "Content-Type: application/json" \
  -d '{"title": "Updated"}'

# Test DELETE
curl -X DELETE http://localhost:8000/books/1
```

Using Swagger UI: Visit http://localhost:8000/docs

### Debugging

**Enable detailed logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

**View database queries (SQLModel):**
```python
import sqlalchemy
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

---

## Summary

This project demonstrates FastAPI best practices:

**Type-safe** - Full type hints for validation and docs \
**Layered architecture** - Separation of concerns (routers → services → models) \
**Exception handling** - Custom exceptions with semantic mapping \ 
**Data validation** - Pydantic schemas with validators \
**ORM usage** - SQLModel for database operations \
**Dependency injection** - Reusable service components \ 
**Auto documentation** - Swagger UI & OpenAPI \
**Middleware support** - Request logging and CORS \  

For more information:
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [SQLModel Documentation](https://sqlmodel.tiangolo.com/)
