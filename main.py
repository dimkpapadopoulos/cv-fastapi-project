from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, status
from sqlmodel import SQLModel, Session, create_engine, select
from models import Job
import time

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
        session.add(job)
        session.commit()

        # Simulate heavy computer vision work taking 10 seconds
        time.sleep(5)

        job.status = "COMPLETED"
        job.result = '{"faces_detected": 2, "confidence": 0.98}'
        session.add(job)
        session.commit()

@app.get("/health")
def health_endpoint():
    return {"status": status.HTTP_200_OK}


@app.post("/jobs/", response_model=Job)
def create_job(task_type: str, background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    # 1. Create the pending job in the DB instantly
    new_job = Job(task_type=task_type)
    session.add(new_job)
    session.commit()
    session.refresh(new_job)

    # 2. Tell FastAPI to run the heavy math in the background
    background_tasks.add_task(process_cv_task, new_job.id)

    # 3. Return the Job ID to the user immediately
    return new_job

@app.get("/jobs/{job_id}", response_model=Job)
def get_job_status(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job