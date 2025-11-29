import os
import time
import threading
import psycopg2
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging
import pandas as pd
import joblib
from datetime import datetime
import numpy as np
import tensorflow as tf

# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
CLASSIFICATION_MODEL_PATH = "heart_risk_model_balanced.pkl"
ANOMALY_MODEL_PATH = "isolation_forest_model.pkl"
FORECASTING_MODEL_PATH = "lstm_forecasting_model.h5"  # Or .h5 if you're using that version
SCALER_PATH = "lstm_data_scaler.pkl"

LABEL_MAP = {0: "Normal", 1: "Stressed", 2: "Fatigued", 3: "Tachycardia", 4: "Bradycardia", 5: "Arrhythmia",
             6: "Hypoxia", 7: "Exercising"}

# --- Model Loading ---
try:
    classification_model = joblib.load(CLASSIFICATION_MODEL_PATH)
    model_features = classification_model.get_booster().feature_names
    anomaly_model = joblib.load(ANOMALY_MODEL_PATH)
    forecasting_model = tf.keras.models.load_model(FORECASTING_MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    logging.info("✅ All models and the data scaler loaded successfully.")
except Exception as e:
    raise RuntimeError(f"❌ Failed to load one or more models: {e}")

# --- FastAPI Application ---
app = FastAPI(title="Multi-Model Prediction Service")


class RawSensorData(BaseModel):
    heart_rate: float;
    spo2: float;
    accel_x: float;
    accel_y: float;
    accel_z: float;
    gyro_x: float;
    gyro_y: float;
    gyro_z: float
    previous_heart_rate: float | None = None
    previous_spo2: float | None = None


# The forecasting endpoint expects a list of readings
class ForecastSequence(BaseModel):
    sequence: list[RawSensorData]


def _engineer_features(data: RawSensorData) -> tuple[pd.DataFrame, dict]:
    hr_diff = data.heart_rate - data.previous_heart_rate if data.previous_heart_rate is not None else 0
    spo2_diff = data.spo2 - data.previous_spo2 if data.previous_spo2 is not None else 0
    hr_spo2_ratio = data.heart_rate / data.spo2 if data.spo2 > 0 else 0
    stress_index = ((data.heart_rate - 75) / 75 * 50) + (abs(hr_diff) * 2) + (max(0, 98 - data.spo2) * 5)
    accel_mag = np.sqrt(data.accel_x ** 2 + data.accel_y ** 2 + data.accel_z ** 2)
    gyro_mag = np.sqrt(data.gyro_x ** 2 + data.gyro_y ** 2 + data.gyro_z ** 2)

    features_dict = {"heart_rate": data.heart_rate, "spo2": data.spo2, "hr_diff": hr_diff, "spo2_diff": spo2_diff,
                     "stress_index": stress_index, "hr_spo2_ratio": hr_spo2_ratio, "accel_mag": accel_mag,
                     "gyro_mag": gyro_mag}
    return pd.DataFrame([features_dict], columns=model_features), features_dict


@app.get("/")
def read_root():
    return {"status": "API is running",
            "models_loaded": [CLASSIFICATION_MODEL_PATH, ANOMALY_MODEL_PATH, FORECASTING_MODEL_PATH]}


def _apply_motion_override(prediction_label: str, engineered_features: dict) -> str:
    """
    Override predictions based on motion data.
    High motion + high HR = Exercise, not Tachycardia
    """
    accel_mag = engineered_features.get("accel_mag", 9.8)
    gyro_mag = engineered_features.get("gyro_mag", 0)
    heart_rate = engineered_features.get("heart_rate", 70)
    
    # High motion threshold: accel_mag > 12 or gyro_mag > 1.0 indicates physical activity
    is_high_motion = accel_mag > 12.0 or gyro_mag > 1.0
    
    # If predicted Tachycardia but user is clearly moving (exercising)
    if prediction_label == "Tachycardia" and is_high_motion and heart_rate < 180:
        logging.info(f"🏃 Motion override: Tachycardia → Exercising (accel_mag={accel_mag:.2f}, gyro_mag={gyro_mag:.2f})")
        return "Exercising"
    
    # If predicted Stressed but high motion suggests exercise
    if prediction_label == "Stressed" and is_high_motion and heart_rate > 100:
        logging.info(f"🏃 Motion override: Stressed → Exercising (accel_mag={accel_mag:.2f}, gyro_mag={gyro_mag:.2f})")
        return "Exercising"
    
    # Very low motion + low HR at rest is normal, not fatigued
    is_resting = accel_mag < 10.0 and gyro_mag < 0.05
    if prediction_label == "Fatigued" and is_resting and 55 <= heart_rate <= 70:
        logging.info(f"😴 Motion override: Fatigued → Normal (resting state)")
        return "Normal"
    
    return prediction_label


@app.post("/predict_classification")
def predict_classification(data: RawSensorData):
    try:
        features_df, engineered_features = _engineer_features(data)
        prediction_result = classification_model.predict(features_df)
        prediction_label = LABEL_MAP.get(int(prediction_result[0]), "Unknown")
        
        # Apply motion-based override logic
        final_prediction = _apply_motion_override(prediction_label, engineered_features)
        
        return {"prediction": final_prediction, "engineered_features": engineered_features}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification error: {str(e)}")


@app.post("/predict_anomaly")
def predict_anomaly(data: RawSensorData):
    try:
        features_df, _ = _engineer_features(data)
        prediction_result = anomaly_model.predict(features_df)
        is_anomaly = bool(prediction_result[0] == -1)
        return {"is_anomaly": is_anomaly}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Anomaly detection error: {str(e)}")


@app.post("/forecast_risk")
def forecast_risk(data: ForecastSequence):
    try:
        if len(data.sequence) != 30:
            raise HTTPException(status_code=400,
                                detail=f"Invalid sequence length. Expected 30, got {len(data.sequence)}")

        feature_list = []
        for reading in data.sequence:
            _, features_dict = _engineer_features(reading)
            feature_list.append(features_dict)

        features_df = pd.DataFrame(feature_list, columns=model_features)
        scaled_features = scaler.transform(features_df)
        sequence = np.array([scaled_features])

        prediction_probs = forecasting_model.predict(sequence)[0]
        prediction_index = np.argmax(prediction_probs)
        prediction_label = LABEL_MAP.get(prediction_index, "Unknown")

        return {"forecasted_prediction": prediction_label}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Forecasting error: {str(e)}")

