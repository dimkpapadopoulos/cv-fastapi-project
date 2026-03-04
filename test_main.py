from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool
import pytest
from unittest.mock import patch

import main

# 1. Setup the blazing-fast in-memory test database
sqlite_url = "sqlite:///:memory:"
engine = create_engine(
    sqlite_url,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)

main.engine = engine
# 2. Create the dependency override
def get_test_session():
    with Session(engine) as session:
        yield session


# Tell FastAPI to swap the real database for the fake one during tests
main.app.dependency_overrides[main.get_session] = get_test_session

client = TestClient(main.app)


# 3. Create the database tables before each test runs
@pytest.fixture(autouse=True)
def setup_db():
    SQLModel.metadata.create_all(engine)
    yield  # The test runs here
    SQLModel.metadata.drop_all(engine)  # Clean up after the test


# --- The Tests ---

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200


# We use @patch to instantly skip the 10-second sleep in our AI function
@patch("main.time.sleep")
def test_create_and_check_job(mock_sleep):
    # 1. Test creating a new job
    response1 = client.post("/jobs/?task_type=face_detection")
    assert response1.status_code == 200

    data = response1.json()
    assert data["task_type"] == "face_detection"
    assert data["status"] == "PENDING"
    assert "id" in data

    job_id = data["id"]

    # 2. Test getting the job status
    # Because TestClient runs background tasks instantly,
    # the status will already be updated to COMPLETED!
    response2 = client.get(f"/jobs/{job_id}")
    assert response2.status_code == 200

    data2 = response2.json()
    assert data2["status"] == "COMPLETED"
    assert data2["result"] == '{"faces_detected": 2, "confidence": 0.98}'


def test_get_nonexistent_job():
    response = client.get("/jobs/fake-uuid-1234")
    assert response.status_code == 404