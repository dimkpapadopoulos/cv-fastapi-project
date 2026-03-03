from fastapi import FastAPI, status

# 1. Initialize the FastAPI application
app = FastAPI(title="Computer Vision API")

# 2. Define our health check route
@app.get("/health")
def health_endpoint():
    return {"status": status.HTTP_200_OK}