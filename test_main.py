from fastapi.testclient import TestClient
from main import *

client = TestClient(app)
def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": status.HTTP_200_OK}