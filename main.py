import ipaddress

from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, status, Request
from sqlmodel import SQLModel, Session, create_engine, select
from models import Job, AccessLog, ResultLog
import time
from datetime import datetime, timedelta, UTC

sqlite_url = "sqlite:///./cv_database.db"
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

app = FastAPI(title="Computer Vision API")

@app.on_event("startup")
def on_startup():
    create_db_and_tables()


def process_cv_task(job_id: str):
    with Session(engine) as session:
        job = session.get(Job, job_id)
        job.status = "PROCESSING"
        start = time.perf_counter()
        session.add(job)
        session.commit()

        time.sleep(5)
        total_time = int((time.perf_counter() - start)*1000)
        job.status = "COMPLETED"
        job.result = '{"faces_detected": 2, "confidence": 0.98}'
        session.add(job)

        log = ResultLog(
            job_id=job.id,
            processing_time_ms=total_time,
            confidence_score=0.98
        )
        session.add(log)
        session.commit()

def check_rate_limit(request: Request, session: Session = Depends(get_session)):
    client_ip = request.client.host
    test_ips = request.headers.get("X-Forwarded-For")
    if test_ips:
        client_ip = test_ips.split(",")[0].strip()
    try:
        ipaddress.ip_address(client_ip)
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad IP Address")

    cutoff_time = (datetime.now(UTC) - timedelta(minutes=30)).replace(tzinfo=None)
    statement = select(AccessLog).where(AccessLog.ip_address == client_ip).order_by(AccessLog.created_at.desc())
    last_request = session.exec(statement).first()

    if last_request and last_request.created_at > cutoff_time:
        wait_time = (last_request.created_at + timedelta(minutes=30)) - datetime.now(UTC).replace(tzinfo=None)
        raise HTTPException(status_code=429, detail=f"Too many requests. Wait for {wait_time.seconds//60} more minutes.")
    new_log = AccessLog(ip_address=client_ip, endpoint=request.url.path)
    session.add(new_log)
    session.commit()

@app.get("/health")
def health_endpoint():
    return {"status": status.HTTP_200_OK}


@app.post("/jobs/", response_model=Job, dependencies=[Depends(check_rate_limit)])
def create_job(task_type: str, background_tasks: BackgroundTasks, session: Session = Depends(get_session)):

    new_job = Job(task_type=task_type)
    session.add(new_job)
    session.commit()
    session.refresh(new_job)

    background_tasks.add_task(process_cv_task, new_job.id)

    return new_job

@app.get("/jobs/{job_id}", response_model=Job)
def get_job_status(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job