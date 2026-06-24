import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Base


@pytest.fixture(scope="session")
def db_engine():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    with Session(db_engine) as session:
        yield session
    with Session(db_engine) as cleanup:
        for table in reversed(Base.metadata.sorted_tables):
            cleanup.execute(table.delete())
        cleanup.commit()
