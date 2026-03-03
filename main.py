from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from sklearn.ensemble import RandomForestClassifier
import joblib
from typing import List

class CustomerChurn(BaseModel):
    account_age_days: int = Field(ge=0)
    total_spend: float

class ChurnRequest(BaseModel):
    customer_id: str
app = FastAPI()

feature_store = {
    "CUST-001": {"account_age_days": 450, "total_spend": 5000.0},
    "CUST-002": {"account_age_days": 30, "total_spend": 150.0}
}

trained_model = RandomForestClassifier()

@app.get("/")
def root_endpoint():
    return {"message": "API is active"}

@app.get("/model-info")
def model_info_endpoint():
    return  {"version": "1.0"}

@app.post("/predict-churn")
def predict_churn_endpoint(customer: CustomerChurn):
    account_age = customer.account_age_days
    total_spend = customer.total_spend
    model_input = [[account_age, total_spend]]

    prediction = trained_model.predict(model_input)
    return {"churn_prediction": bool(prediction[0])}

@app.post("/predict-churn-batch")
def predict_churn_endpoint(customer_list: List[CustomerChurn]):

    model_input = [[customer.account_age_days, customer.total_spend] for customer in customer_list]

    predictions = trained_model.predict(model_input)
    return {"churn_predictions": [bool(pred) for pred in predictions]}

@app.post("/predict-churn-by-id")
def predict_by_id_endpoint(request: ChurnRequest):
    cid = request.customer_id
    try:
       cinfo = feature_store[cid]
       model_input = [[cinfo['account_age_days'], cinfo['total_spend']]]
    except KeyError as e:
        raise HTTPException(404, detail=f"Customer ID '{cid}' not found in feature store.")
    prediction = trained_model.predict(model_input)
    return {"churn_prediction": bool(prediction[0])}
status.HTTP_200_OK