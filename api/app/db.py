"""Database engine and session helpers."""

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


def normalise(url: str) -> str:
    """
    Make a hosted Postgres URL something SQLAlchemy will actually accept.

    Neon, Render and Heroku hand out `postgres://`, which SQLAlchemy 2 rejects
    outright. And plain `postgresql://` picks psycopg2, which isn't installed —
    this project uses psycopg 3. Both are a confusing first deploy otherwise.
    """
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


database_url = normalise(settings.database_url)

# check_same_thread is a SQLite-only quirk: FastAPI serves requests on
# different threads and SQLite blocks that by default.
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}

engine = create_engine(database_url, connect_args=connect_args)


def create_tables() -> None:
    """Create any tables that don't exist yet."""
    # Importing models registers them on SQLModel.metadata before we create.
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency — one session per request, closed automatically."""
    with Session(engine) as session:
        yield session
