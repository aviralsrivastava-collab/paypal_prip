from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.core.config import get_settings

settings = get_settings()


def get_engine_kwargs(database_url: str) -> Dict[str, Any]:
    """Returns engine keyword arguments based on dialect and settings."""
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {
        "pool_size": settings.database_pool_size,
        "max_overflow": settings.database_max_overflow,
        "pool_timeout": settings.database_pool_timeout,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }


def create_app_engine(database_url: str) -> Engine:
    """Creates a database engine with dialect-appropriate pooling."""
    kwargs = get_engine_kwargs(database_url)
    return create_engine(
        database_url,
        **kwargs,
        echo=(settings.app_env == "development_debug"),
    )


def init_db_engine(database_url: Optional[str] = None) -> Engine:
    """
    Initializes database engine with strict failure semantics.
    In production: fails closed immediately without fallback.
    In non-production: falls back to SQLite for local development convenience.
    """
    target_url = database_url or settings.database_url
    try:
        return create_app_engine(target_url)
    except Exception as exc:
        if settings.app_env.lower() == "production":
            raise RuntimeError(
                f"Production database connection failed: {exc}. Engine fails closed without fallback."
            ) from exc
        return create_engine("sqlite:///./prip_demo.db", connect_args={"check_same_thread": False})


engine = init_db_engine()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def atomic_transaction(session: Session) -> Generator[Session, None, None]:
    """
    Context manager providing atomic transaction boundaries.
    Commits on successful block execution; rolls back on any unhandled exception.
    """
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise

