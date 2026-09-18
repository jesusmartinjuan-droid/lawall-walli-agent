import os
import tempfile

# Must be set before app.core.config.settings (a module-level singleton) is
# ever imported, so every test module gets a consistent, test-safe config.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENCRYPTION_KEY", "wz2X3n8Q4bqjE6y9m1TmvY6C2kZ8b1f3o8s5j9d0Uqk=")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("LLM_PROVIDER", "mock")
# The production default (/app/storage/documents) only exists inside the
# Docker container; tests that upload documents/images need a real writable
# directory on whatever machine runs the suite.
os.environ.setdefault("DOCUMENTS_STORAGE_PATH", tempfile.mkdtemp(prefix="walli-test-storage-"))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base_all import Base


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
