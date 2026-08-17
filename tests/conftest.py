import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth import hash_api_key
from app.core.rate_limit import reset_all as reset_rate_limits
from app.db import session as db_session
from app.main import app
from app.models.tenant import Tenant
from app.models.widget import Widget

# Separate test database so tests never touch dev data. Created fresh, and
# schema is rebuilt every test run for determinism.
TEST_DATABASE_URL = "postgresql+psycopg2://widget_user:widget_pass@localhost:5432/widget_platform_test"


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL)
    db_session.Base.metadata.drop_all(bind=eng)
    db_session.Base.metadata.create_all(bind=eng)
    yield eng
    db_session.Base.metadata.drop_all(bind=eng)


@pytest.fixture()
def db(engine):
    """Fresh session per test; tables are truncated after each test so
    tests don't leak state into each other."""
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.rollback()
    for table in reversed(db_session.Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()
    reset_rate_limits()


@pytest.fixture()
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[db_session.get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def tenant(db):
    raw_key = "test-api-key-" + uuid.uuid4().hex[:8]
    t = Tenant(name="Test Tenant", api_key_hash=hash_api_key(raw_key))
    db.add(t)
    db.commit()
    db.refresh(t)
    return t, raw_key


@pytest.fixture()
def widget(db, tenant):
    t, _ = tenant
    w = Widget(
        tenant_id=t.id,
        type="signup_form",
        title="Test Widget",
        fields=[{"name": "email", "label": "Email", "type": "email", "required": True}],
        button_text="Go",
        display_options={},
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return w
