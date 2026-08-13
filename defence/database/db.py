import logging
 
from sqlalchemy.pool import NullPool
from sqlmodel import Session, create_engine
 
from core.config import settings
 
logger = logging.getLogger(__name__)

if settings.DATABASE_URL == None : 
    raise ValueError("Database Connection String NOT FOUND")

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    poolclass=NullPool,           # Supabase manages pooling server-side
    connect_args={
        "options": "-c statement_timeout=30000",  # 30s query timeout
    },
)

def verify_connection() -> None:
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def create_db_and_tables() -> None:
    """
    Create the core SQLModel tables if they don't already exist.

    This is a development convenience so a fresh database (e.g. a new Supabase
    project) works out of the box. It is idempotent — existing tables are left
    untouched (create_all uses checkfirst=True).

    NOTE: the RAG pgvector table (``book_chunks``) and the ``match_book_chunks``
    function are NOT created here — they need the pgvector extension and must
    be provisioned via ``sql/rag_setup.sql``.
    """
    from sqlmodel import SQLModel

    # Import every table model so it registers on SQLModel.metadata before
    # create_all runs. (Routers import these too, but we import explicitly so
    # this function is correct regardless of import order.)
    import models.book          # noqa: F401
    import models.member        # noqa: F401
    import models.loan          # noqa: F401
    import models.conversation  # noqa: F401
    import models.book_embedding  # noqa: F401

    SQLModel.metadata.create_all(engine)
 
def get_session():
    with Session(engine) as session:
        yield session