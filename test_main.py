from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select
from sqlmodel.pool import StaticPool
import pytest
from unittest.mock import patch
from models import ResultLog, AccessLog
import main
from datetime import datetime, UTC, timedelta
from PIL import Image
import io
import tempfile

sqlite_url = "sqlite:///:memory:"
engine = create_engine(
    sqlite_url,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)

main.engine = engine

def get_test_session():
    with Session(engine) as session:
        yield session


main.app.dependency_overrides[main.get_session] = get_test_session

client = TestClient(main.app)

@pytest.fixture(scope="session")
def valid_image_bytes():
    # Create a 100x100 solid red image in memory
    img = Image.new('RGB', (100, 100), color='red')
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    return img_byte_arr.getvalue()

@pytest.fixture(autouse=True)
def setup_test_uploads():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_upload_dir = main.UPLOAD_DIR
        main.UPLOAD_DIR = tmpdir
        yield
        main.UPLOAD_DIR = original_upload_dir

@pytest.fixture(autouse=True)
def setup_db():
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200


@patch("main.time.sleep")
def test_create_and_check_job(mockwait, valid_image_bytes):
    form_data = {"task_type": "face_recognition"}
    dummy_file = {"file": ("test_image.jpg", valid_image_bytes, "image/jpeg")}
    response1 = client.post(
        "/jobs/",
        data=form_data,
        files=dummy_file,
        headers={"X-Forwarded-For": "1.2.3.4"}
    )
    assert response1.status_code == 200

    data = response1.json()
    assert data["task_type"] == "face_recognition"
    assert data["status"] == "PENDING"
    assert "id" in data

    job_id = data["id"]

    response2 = client.get(f"/jobs/{job_id}")
    assert response2.status_code == 200

    data2 = response2.json()
    assert data2["status"] == "COMPLETED"

    with Session(engine) as session:
        statement = select(ResultLog).where(ResultLog.job_id == job_id)
        result_log = session.exec(statement).first()
        assert result_log is not None
        assert result_log.job_id == job_id
        assert result_log.processing_time_ms >= 0

def test_get_nonexistent_job():
    response = client.get("/jobs/fake-uuid-1234")
    assert response.status_code == 404

def test_rate_limit_blocks_immediate_second_request(valid_image_bytes):
    form_data = {"task_type": "face_recognition"}

    file1 = {"file": ("test.jpg", valid_image_bytes, "image/jpeg")}
    response1 = client.post("/jobs/", data=form_data, files=file1, headers={"X-Forwarded-For": "10.0.0.1"})
    assert response1.status_code == 200

    file2 = {"file": ("test.jpg", b"dummy content", "image/jpeg")}
    response2 = client.post("/jobs/", data=form_data, files=file2, headers={"X-Forwarded-For": "10.0.0.1"})
    assert response2.status_code == 429
    assert "Too many requests" in response2.json()["detail"]


def test_rate_limit_blocks_just_before_cutoff(valid_image_bytes):

    past_time = (datetime.now(UTC) - timedelta(minutes=2, seconds=59)).replace(tzinfo=None)
    old_log = AccessLog(ip_address="10.0.0.2", endpoint="/jobs/", created_at=past_time)

    with Session(engine) as session:
        session.add(old_log)
        session.commit()

    form_data = {"task_type": "face_recognition"}
    dummy_file = {"file": ("test.jpg", valid_image_bytes, "image/jpeg")}

    response = client.post("/jobs/", data=form_data, files=dummy_file, headers={"X-Forwarded-For": "10.0.0.2"})
    assert response.status_code == 429
    assert "Too many requests" in response.json()["detail"]


def test_rate_limit_allows_just_after_cutoff(valid_image_bytes):

    past_time = (datetime.now(UTC) - timedelta(minutes=3, seconds=1)).replace(tzinfo=None)
    old_log = AccessLog(ip_address="10.0.0.3", endpoint="/jobs/", created_at=past_time)

    with Session(engine) as session:
        session.add(old_log)
        session.commit()

    form_data = {"task_type": "face_recognition"}
    dummy_file = {"file": ("test.jpg", valid_image_bytes, "image/jpeg")}

    response = client.post("/jobs/", data=form_data, files=dummy_file, headers={"X-Forwarded-For": "10.0.0.3"})
    assert response.status_code == 200

def test_malformed_ip(valid_image_bytes):
    malformed_ip_list = ["not-an-ip", "1.2.3.four", "1.3.5.512", "1.2.3.4.5.6"]
    form_data = {"task_type": "face_recognition"}
    for ip in malformed_ip_list:
        dummy_file = {"file": ("test.jpg", valid_image_bytes, "image/jpeg")}
        response = client.post("/jobs/", data=form_data, files=dummy_file, headers={"X-Forwarded-For": ip})
        assert response.status_code == 400
        assert response.json()["detail"] == "Bad IP Address"
