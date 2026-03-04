from fastapi.params import Depends
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select
from sqlmodel.pool import StaticPool
import pytest
from unittest.mock import patch
from models import Job, ResultLog, AccessLog
import main
from datetime import datetime, UTC, timedelta
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


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200


@patch("main.time.sleep")
def test_create_and_check_job(mock_sleep):

    response1 = client.post("/jobs/?task_type=face_detection", headers={"X-Forwarded-For": "1.2.3.4"})
    assert response1.status_code == 200

    data = response1.json()
    assert data["task_type"] == "face_detection"
    assert data["status"] == "PENDING"
    assert "id" in data

    job_id = data["id"]

    response2 = client.get(f"/jobs/{job_id}")
    assert response2.status_code == 200

    data2 = response2.json()
    assert data2["status"] == "COMPLETED"
    assert data2["result"] == '{"faces_detected": 2, "confidence": 0.98}'
    with Session(engine) as session:
        statement = select(ResultLog).where(ResultLog.job_id == job_id)
        result_log = session.exec(statement).first()
        assert result_log is not None
        assert result_log.job_id == job_id
        assert result_log.processing_time_ms >= 0

def test_get_nonexistent_job():
    response = client.get("/jobs/fake-uuid-1234")
    assert response.status_code == 404


def test_rate_limit_blocks_second_request():
    # 1. First request should succeed
    response1 = client.post("/jobs/?task_type=face_detection", headers={"X-Forwarded-For": "1.2.4.3"})
    assert response1.status_code == 200

    # 2. Second request from the same "IP" should fail
    response2 = client.post("/jobs/?task_type=face_detection", headers={"X-Forwarded-For": "1.2.4.3"})
    assert response2.status_code == 429
    assert "Too many requests" in response2.json()["detail"]

def test_rate_limit_jit():
    past_time = (datetime.now(UTC) - timedelta(minutes=30, seconds=1)).replace(tzinfo=None)
    old_log = AccessLog(ip_address="1.2.2.1", endpoint="/jobs/", created_at=past_time)
    with Session(engine) as session:
        session.add(old_log)
        session.commit()
    response = client.post("/jobs/?task_type=face_detection", headers={"X-Forwarded-For": "1.2.3.1"})
    assert response.status_code == 200

def test_malformed_ip():
    malformed_ip_list = ["not-an-ip", "1.2.3.four", "1.3.5.512", "1.2.3.4.5.6"]
    for ip in malformed_ip_list:
        response = client.post("/jobs/?task_type=face_detection", headers={"X-Forwarded-For": ip})
        assert response.status_code == 400
        assert response.json()["detail"] == "Bad IP Address"
