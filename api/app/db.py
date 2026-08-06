"""Database engine and session helpers."""

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

# check_same_thread is a SQLite-only quirk: FastAPI serves requests on
# different threads and SQLite blocks that by default.
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)


def create_tables() -> None:
    """Create any tables that don't exist yet."""
    # Importing models registers them on SQLModel.metadata before we create.
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency — one session per request, closed automatically."""
    with Session(engine) as session:
        yield session
