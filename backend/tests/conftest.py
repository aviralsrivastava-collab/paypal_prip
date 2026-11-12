from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

import backend.models  # noqa: F401
from backend.api.main import app
from backend.core.database import Base, get_db
from backend.core.rate_limit import reset_rate_limit_store

TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_rate_limits() -> Generator[None, None, None]:
    """Ensures each test execution starts with a fresh rate limiting bucket."""
    reset_rate_limit_store()
    yield
    reset_rate_limit_store()


@pytest.fixture(autouse=True)
def enforce_mock_paypal_for_unit_tests(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Ensures unit test suites use deterministic mock PayPal client regardless of local .env configuration."""
    monkeypatch.setenv("PAYPAL_CLIENT_TYPE", "mock")
    from backend.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
