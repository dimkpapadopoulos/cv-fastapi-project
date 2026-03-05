from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, status, Request, Form, File, UploadFile
from sqlmodel import SQLModel, Session, create_engine, select
from models import Job, AccessLog, ResultLog
from PIL import Image, ImageDraw
import numpy as np
import mediapipe as mp
from datetime import datetime, timedelta, UTC
import time
import ipaddress
import shutil
import os
import json

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
templates = Jinja2Templates(directory="templates")
sqlite_url = "sqlite:///./cv_database.db"
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

app = FastAPI(title="Computer Vision API")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount('/uploads', StaticFiles(directory="uploads"), name="uploads")
@app.on_event("startup")
def on_startup():
    create_db_and_tables()

def face_recognition(file_path: str, job_id: str):

    model_path = 'blaze_face_short_range.tflite'
    output_file = os.path.join(UPLOAD_DIR, f"{job_id}_result.jpg")

    BaseOptions = mp.tasks.BaseOptions
    FaceDetector = mp.tasks.vision.FaceDetector
    FaceDetectorOptions = mp.tasks.vision.FaceDetectorOptions
    VisionRunningMode = mp.tasks.vision.RunningMode
    options = FaceDetectorOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=VisionRunningMode.IMAGE)

    with FaceDetector.create_from_options(options) as detector:
        try:
            img = Image.open(file_path).convert('RGB')

            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.array(img))

            results = detector.detect(mp_image)

            draw = ImageDraw.Draw(img)
            if results.detections:
                faces_detected = len(results.detections)

                for det in results.detections:
                    bbox = det.bounding_box

                    x, y = int(bbox.origin_x), int(bbox.origin_y)
                    w, h = int(bbox.width), int(bbox.height)

                    draw.rectangle([(x, y), (x + w, y + h)], outline="red", width=3)

                print("Saving the image")
                img.save(output_file)
                return f"/uploads/{job_id}_result.jpg"
            else:
                return None
        except Exception as e:
            print(f"Failed to proces image: {e}")


def image_segmentation(file_path: str, job_id: str):

    output_file = os.path.join(UPLOAD_DIR, f"{job_id}_result.jpg")
    model_path = 'deeplab_v3.tflite'

    BaseOptions = mp.tasks.BaseOptions
    ImageSegmenter = mp.tasks.vision.ImageSegmenter
    ImageSegmenterOptions = mp.tasks.vision.ImageSegmenterOptions
    VisionRunningMode = mp.tasks.vision.RunningMode

    options = ImageSegmenterOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=VisionRunningMode.IMAGE,
        output_category_mask=True
    )

    with ImageSegmenter.create_from_options(options) as segmenter:
        try:
            original_img = Image.open(file_path).convert('RGBA')
            img_for_mp = original_img.convert('RGB')
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.array(img_for_mp))

            segmentation_result = segmenter.segment(mp_image)

            if segmentation_result.category_mask is not None:
                mask_array = segmentation_result.category_mask.numpy_view()
                if len(mask_array.shape) == 3:
                    mask_array = mask_array.squeeze()
                mask_uint8 = mask_array.astype(np.uint8)
                # Create a color palette mask for visualization
                colored_mask = Image.fromarray(mask_uint8, mode='P')

                # Generate random colors for the different segments
                np.random.seed(42)
                palette = np.random.randint(0, 256, 768).tolist()
                palette[0:3] = [0, 0, 0]  # Make background black/transparent
                colored_mask.putpalette(palette)
                mask_rgba = colored_mask.convert('RGBA')

                # Blend the original image with the colored mask overlay
                final_img = Image.blend(original_img, mask_rgba, alpha=0.6)
                final_img.convert('RGB').save(output_file)

                return f"/uploads/{job_id}_result.jpg"
            else:
                return None
        except Exception as e:
            print(f"Failed to process image: {e}")
            return None


def process_cv_task(job_id: str, file_path: str):
    with Session(engine) as session:

        job = session.get(Job, job_id)
        job.status = "PROCESSING"

        start = time.perf_counter()
        end = 0

        session.add(job)
        session.commit()

        if job.task_type == 'face_recognition':
            result = face_recognition(file_path, job_id)
            end = time.perf_counter()
            job.status = "COMPLETED"
            job.result = json.dumps({"result_image": result})
        elif job.task_type == "segmentation":
            result = image_segmentation(file_path, job_id)
            end = time.perf_counter()
            job.status = "COMPLETED"
            job.result = json.dumps({"result_image": result})

        session.add(job)

        log = ResultLog(
            job_id=job.id,
            processing_time_ms=int((end-start)*1000),
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
    limit_minutes = 3
    cutoff_time = (datetime.now(UTC) - timedelta(minutes=limit_minutes)).replace(tzinfo=None)
    print("CUTOFF TIME: ", cutoff_time)
    statement = select(AccessLog).where(AccessLog.ip_address == client_ip).order_by(AccessLog.created_at.desc())
    last_request = session.exec(statement).first()
    if last_request and last_request.created_at > cutoff_time:
        wait_time = (last_request.created_at + timedelta(minutes=limit_minutes)) - datetime.now(UTC).replace(tzinfo=None)
        print("WAIT TIME: ", wait_time)
        if wait_time > timedelta(seconds=0):
            raise HTTPException(status_code=429, detail=f"Too many requests. Time to next request: {wait_time.seconds} seconds")
    new_log = AccessLog(ip_address=client_ip, endpoint=request.url.path)
    session.add(new_log)
    session.commit()

@app.get("/", response_class=HTMLResponse)
def upload_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
def health_endpoint():
    return {"status": status.HTTP_200_OK}

@app.post("/jobs/", response_model=Job, dependencies=[Depends(check_rate_limit)])
def create_job(
        background_tasks: BackgroundTasks,
        task_type: str = Form(...),
        file: UploadFile = File(...),
        session: Session = Depends(get_session)):

    new_job = Job(task_type=task_type)
    session.add(new_job)
    session.commit()
    session.refresh(new_job)

    file_ext = file.filename.split(".")[-1]
    file_path = os.path.join(UPLOAD_DIR, f"{new_job.id}.{file_ext}")

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    background_tasks.add_task(process_cv_task, new_job.id, file_path)

    return new_job

@app.get("/jobs/{job_id}", response_model=Job)
def get_job_status(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get('/jobs/{job_id}/image')
def get_job_image(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "COMPLETED":
        raise HTTPException(status_code=400, detail="Job is not completed yet")
    file_path = os.path.join(UPLOAD_DIR, f"{job.id}_result.jpg")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        file_path,
        media_type="image/jpeg",
        filename=f"{job.task_type}_result_{job_id}.jpg"
    )