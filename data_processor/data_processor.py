import os
import time
import threading
import psycopg2
import requests
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import logging
import pandas as pd
import joblib
from datetime import datetime, timedelta
import json
import asyncio

# JWT Auth
from jose import JWTError, jwt
from passlib.context import CryptContext

# Firebase (optional - can be enabled later)
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    FIREBASE_ENABLED = False  # Set to True when you have firebase-service-account.json
except ImportError:
    FIREBASE_ENABLED = False

# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DB_HOST = "db"
DB_NAME = os.getenv("POSTGRES_DB")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASS = os.getenv("POSTGRES_PASSWORD")

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET", "pulsai-super-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

# ML API URLs
CLASSIFICATION_API_URL = "http://ml-api:8000/predict_classification"
ANOMALY_API_URL = "http://ml-api:8000/predict_anomaly"
FORECASTING_API_URL = "http://ml-api:8000/forecast_risk"

LOOKBACK_WINDOW = 30
CLUSTERING_INTERVAL_SECONDS = 3600
SUMMARY_INTERVAL_SECONDS = 86400

# Password hashing - using argon2 as fallback, then bcrypt
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# Firebase initialization (optional)
if FIREBASE_ENABLED:
    try:
        cred = credentials.Certificate("/app/firebase-service-account.json")
        firebase_admin.initialize_app(cred)
        logging.info("✅ Firebase initialized")
    except Exception as e:
        logging.warning(f"⚠️ Firebase initialization failed: {e}")
        FIREBASE_ENABLED = False

# Load clustering models
try:
    dbscan_model = joblib.load("dbscan_model.pkl")
    dbscan_scaler = joblib.load("dbscan_scaler.pkl")
    logging.info("✅ DBSCAN model and scaler loaded.")
except FileNotFoundError:
    dbscan_model, dbscan_scaler = None, None
    logging.warning("⚠️ DBSCAN models not found. Clustering disabled.")

# --- FastAPI App ---
app = FastAPI(title="PulsAI Data Processing & API Service")

# CORS - Allow mobile app connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models ---
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    phone: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class DeviceRegistration(BaseModel):
    device_id: str
    fcm_token: Optional[str] = None
    expo_push_token: Optional[str] = None
    platform: str = "android"
    device_name: Optional[str] = None

class RawSensorData(BaseModel):
    heart_rate: float
    spo2: float
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float

class RawSensorDataWithDevice(RawSensorData):
    device_id: str

class EmergencyContact(BaseModel):
    name: str
    phone: str
    relationship: Optional[str] = None
    is_primary: bool = False

class UserSettings(BaseModel):
    low_spo2_threshold: float = 92.0
    high_hr_threshold: float = 120.0
    low_hr_threshold: float = 50.0
    enable_predictive_alerts: bool = True
    enable_anomaly_alerts: bool = True
    enable_emergency_alerts: bool = True
    enable_sound: bool = True
    enable_vibration: bool = True

CLUSTER_NAME_MAP = {-1: "Noise/Undefined", 0: "Resting", 1: "Light Activity", 2: "Moderate Activity", 3: "Commuting"}

# --- Database Connection ---
def get_db_connection():
    if not all([DB_NAME, DB_USER, DB_PASS]):
        raise ConnectionError("Missing DB credentials")
    return psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS)

# --- Auth Helpers ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        # Truncate to 72 bytes for bcrypt limit
        password = plain_password[:72]
        return pwd_context.verify(password, hashed_password)
    except Exception as e:
        logging.error(f"Password verification error: {e}")
        return False

def get_password_hash(password: str) -> str:
    # Truncate to 72 bytes for bcrypt limit
    return pwd_context.hash(password[:72])

def create_access_token(user_id: int, email: str) -> str:
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode = {"sub": str(user_id), "email": email, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        email = payload.get("email")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"id": user_id, "email": email}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

async def get_optional_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        return None
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        email = payload.get("email")
        return {"id": user_id, "email": email}
    except JWTError:
        return None

# --- WebSocket Connection Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, device_id: str):
        await websocket.accept()
        self.active_connections[device_id] = websocket
        logging.info(f"WebSocket connected: {device_id}")

    def disconnect(self, device_id: str):
        if device_id in self.active_connections:
            del self.active_connections[device_id]
            logging.info(f"WebSocket disconnected: {device_id}")

    async def send_to_device(self, device_id: str, message: dict):
        if device_id in self.active_connections:
            try:
                await self.active_connections[device_id].send_json(message)
            except Exception as e:
                logging.error(f"WebSocket send error: {e}")

    async def broadcast_to_user(self, user_id: int, message: dict):
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT device_id FROM devices WHERE user_id = %s AND is_active = TRUE", (user_id,))
                    devices = cur.fetchall()
                    for (device_id,) in devices:
                        await self.send_to_device(device_id, message)
        except Exception as e:
            logging.error(f"Broadcast error: {e}")

manager = ConnectionManager()

# ===================== AUTH ENDPOINTS =====================

@app.post("/api/v1/auth/register", response_model=TokenResponse)
def register_user(user: UserRegister):
    """Register a new user account"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE email = %s", (user.email,))
                if cur.fetchone():
                    raise HTTPException(status_code=400, detail="Email already registered")
                
                password_hash = get_password_hash(user.password)
                cur.execute(
                    "INSERT INTO users (email, password_hash, full_name, phone) VALUES (%s, %s, %s, %s) RETURNING id",
                    (user.email, password_hash, user.full_name, user.phone)
                )
                user_id = cur.fetchone()[0]
                
                cur.execute("INSERT INTO user_settings (user_id) VALUES (%s)", (user_id,))
                conn.commit()
                
                token = create_access_token(user_id, user.email)
                return {
                    "access_token": token,
                    "token_type": "bearer",
                    "user": {"id": user_id, "email": user.email, "full_name": user.full_name}
                }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Registration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/auth/login", response_model=TokenResponse)
def login_user(credentials: UserLogin):
    """Login with email and password"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, email, password_hash, full_name FROM users WHERE email = %s AND is_active = TRUE",
                    (credentials.email,)
                )
                row = cur.fetchone()
                if not row or not verify_password(credentials.password, row[2]):
                    raise HTTPException(status_code=401, detail="Invalid email or password")
                
                user_id, email, _, full_name = row
                token = create_access_token(user_id, email)
                return {
                    "access_token": token,
                    "token_type": "bearer",
                    "user": {"id": user_id, "email": email, "full_name": full_name}
                }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Login failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/auth/me")
def get_current_user_info(user: dict = Depends(get_current_user)):
    """Get current authenticated user info"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, email, full_name, phone, created_at FROM users WHERE id = %s",
                    (user["id"],)
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="User not found")
                return {
                    "id": row[0],
                    "email": row[1],
                    "full_name": row[2],
                    "phone": row[3],
                    "created_at": row[4].isoformat() if row[4] else None
                }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===================== DEVICE ENDPOINTS =====================

@app.post("/api/v1/devices/register")
def register_device(registration: DeviceRegistration, user: dict = Depends(get_current_user)):
    """Register a device for push notifications"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                sql = """
                    INSERT INTO devices (device_id, user_id, fcm_token, expo_push_token, platform, device_name, last_seen)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (device_id) DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        fcm_token = EXCLUDED.fcm_token,
                        expo_push_token = EXCLUDED.expo_push_token,
                        platform = EXCLUDED.platform,
                        device_name = EXCLUDED.device_name,
                        last_seen = NOW(),
                        is_active = TRUE
                """
                cur.execute(sql, (
                    registration.device_id,
                    user["id"],
                    registration.fcm_token,
                    registration.expo_push_token,
                    registration.platform,
                    registration.device_name
                ))
                conn.commit()
        return {"status": "registered", "device_id": registration.device_id}
    except Exception as e:
        logging.error(f"Device registration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/devices")
def get_user_devices(user: dict = Depends(get_current_user)):
    """Get all devices registered to current user"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT device_id, device_name, platform, last_seen, is_active FROM devices WHERE user_id = %s",
                    (user["id"],)
                )
                rows = cur.fetchall()
                return [
                    {
                        "device_id": r[0],
                        "device_name": r[1],
                        "platform": r[2],
                        "last_seen": r[3].isoformat() if r[3] else None,
                        "is_active": r[4]
                    }
                    for r in rows
                ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===================== HEALTH DATA ENDPOINTS =====================

@app.post("/ingest")
def ingest_data(reading: RawSensorData):
    """Legacy ingest endpoint (without device_id)"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                sql = "INSERT INTO smartwatch_readings (heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                cur.execute(sql, (reading.heart_rate, reading.spo2, reading.accel_x, reading.accel_y, reading.accel_z,
                                  reading.gyro_x, reading.gyro_y, reading.gyro_z))
                conn.commit()
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/ingest")
def ingest_data_v2(reading: RawSensorDataWithDevice, user: dict = Depends(get_optional_user)):
    """Ingest sensor data with device_id"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                sql = """
                    INSERT INTO smartwatch_readings 
                    (device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cur.execute(sql, (
                    reading.device_id, reading.heart_rate, reading.spo2,
                    reading.accel_x, reading.accel_y, reading.accel_z,
                    reading.gyro_x, reading.gyro_y, reading.gyro_z
                ))
                
                cur.execute("UPDATE devices SET last_seen = NOW() WHERE device_id = %s", (reading.device_id,))
                conn.commit()
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/health/latest")
def get_latest_reading(user: dict = Depends(get_current_user)):
    """Get latest health reading for the authenticated user"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT sr.time, sr.device_id, sr.heart_rate, sr.spo2, sr.prediction, sr.is_anomaly, 
                           sr.forecasted_prediction, sr.stress_index, sr.cluster_label, sr.accel_mag
                    FROM smartwatch_readings sr
                    JOIN devices d ON sr.device_id = d.device_id
                    WHERE d.user_id = %s 
                    ORDER BY sr.time DESC LIMIT 1
                """, (user["id"],))
                row = cur.fetchone()
                if not row:
                    return {"message": "No data found", "data": None}
                
                return {
                    "time": row[0].isoformat() if row[0] else None,
                    "device_id": row[1],
                    "heart_rate": row[2],
                    "spo2": row[3],
                    "prediction": row[4],
                    "is_anomaly": row[5],
                    "forecasted_prediction": row[6],
                    "stress_index": row[7],
                    "cluster_label": row[8],
                    "accel_mag": row[9]
                }
    except Exception as e:
        logging.error(f"Failed to get latest reading: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/health/history")
def get_health_history(hours: int = 24, limit: int = 500, user: dict = Depends(get_current_user)):
    """Get health history for authenticated user"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT sr.time, sr.heart_rate, sr.spo2, sr.prediction, sr.is_anomaly, 
                           sr.forecasted_prediction, sr.stress_index, sr.accel_mag
                    FROM smartwatch_readings sr
                    JOIN devices d ON sr.device_id = d.device_id
                    WHERE d.user_id = %s AND sr.time >= NOW() - INTERVAL '%s hours'
                    ORDER BY sr.time DESC LIMIT %s
                """, (user["id"], hours, limit))
                rows = cur.fetchall()
                columns = ['time', 'heart_rate', 'spo2', 'prediction', 'is_anomaly',
                          'forecasted_prediction', 'stress_index', 'accel_mag']
                return [
                    {**dict(zip(columns, row)), "time": row[0].isoformat() if row[0] else None}
                    for row in rows
                ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/summary")
def get_daily_summary():
    """Legacy summary endpoint"""
    summary = {}
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT prediction, COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () FROM smartwatch_readings WHERE time >= NOW() - INTERVAL '24 hours' AND prediction IS NOT NULL GROUP BY prediction;")
                summary['state_distribution_percent'] = {state: round(percent, 2) for state, percent in cur.fetchall()}
                cur.execute(
                    "SELECT COUNT(*) FROM smartwatch_readings WHERE time >= NOW() - INTERVAL '24 hours' AND is_anomaly = TRUE;")
                summary['anomaly_count'] = cur.fetchone()[0]
                cur.execute(
                    "SELECT AVG(heart_rate) FROM smartwatch_readings WHERE time >= NOW() - INTERVAL '24 hours' AND accel_mag < 10.5;")
                avg_hr = cur.fetchone()[0]
                summary['average_resting_hr'] = round(avg_hr, 1) if avg_hr else None
                cur.execute(
                    "SELECT cluster_label, COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () FROM smartwatch_readings WHERE time >= NOW() - INTERVAL '24 hours' AND cluster_label IS NOT NULL AND cluster_label != 'Noise/Undefined' GROUP BY cluster_label;")
                summary['activity_distribution_percent'] = {label: round(percent, 2) for label, percent in cur.fetchall()}
        return summary
    except Exception as e:
        logging.error(f"Summary generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Could not generate summary: {e}")

@app.get("/api/v1/health/summary")
def get_user_summary(user: dict = Depends(get_current_user)):
    """Get health summary for authenticated user"""
    summary = {}
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT device_id FROM devices WHERE user_id = %s", (user["id"],))
                device_ids = [r[0] for r in cur.fetchall()]
                
                if not device_ids:
                    return {"message": "No devices registered", "data": None}
                
                placeholders = ','.join(['%s'] * len(device_ids))
                
                cur.execute(f"""
                    SELECT prediction, COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () 
                    FROM smartwatch_readings 
                    WHERE time >= NOW() - INTERVAL '24 hours' 
                    AND prediction IS NOT NULL 
                    AND device_id IN ({placeholders})
                    GROUP BY prediction
                """, device_ids)
                summary['state_distribution_percent'] = {state: round(percent, 2) for state, percent in cur.fetchall()}
                
                cur.execute(f"""
                    SELECT COUNT(*) FROM smartwatch_readings 
                    WHERE time >= NOW() - INTERVAL '24 hours' 
                    AND is_anomaly = TRUE 
                    AND device_id IN ({placeholders})
                """, device_ids)
                summary['anomaly_count'] = cur.fetchone()[0]
                
                cur.execute(f"""
                    SELECT AVG(heart_rate) FROM smartwatch_readings 
                    WHERE time >= NOW() - INTERVAL '24 hours' 
                    AND accel_mag < 10.5 
                    AND device_id IN ({placeholders})
                """, device_ids)
                avg_hr = cur.fetchone()[0]
                summary['average_resting_hr'] = round(avg_hr, 1) if avg_hr else None
                
                cur.execute(f"""
                    SELECT cluster_label, COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () 
                    FROM smartwatch_readings 
                    WHERE time >= NOW() - INTERVAL '24 hours' 
                    AND cluster_label IS NOT NULL 
                    AND cluster_label != 'Noise/Undefined' 
                    AND device_id IN ({placeholders})
                    GROUP BY cluster_label
                """, device_ids)
                summary['activity_distribution_percent'] = {label: round(percent, 2) for label, percent in cur.fetchall()}
                
        return summary
    except Exception as e:
        logging.error(f"Summary generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/summary/trends")
def get_health_trends():
    """Legacy trends endpoint"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM health_summaries ORDER BY summary_date DESC LIMIT 30")
                trends = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in trends]
    except Exception as e:
        logging.error(f"Trend retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Could not retrieve trends: {e}")

# ===================== ALERTS/NOTIFICATIONS ENDPOINTS =====================

@app.get("/api/v1/alerts")
def get_user_alerts(limit: int = 50, unread_only: bool = False, user: dict = Depends(get_current_user)):
    """Get alerts/notifications for authenticated user"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT id, notification_type, title, body, data, sent_at, read_at
                    FROM notifications 
                    WHERE user_id = %s
                """
                if unread_only:
                    query += " AND read_at IS NULL"
                query += " ORDER BY sent_at DESC LIMIT %s"
                
                cur.execute(query, (user["id"], limit))
                rows = cur.fetchall()
                return [
                    {
                        "id": r[0],
                        "type": r[1],
                        "title": r[2],
                        "body": r[3],
                        "data": r[4],
                        "sent_at": r[5].isoformat() if r[5] else None,
                        "read_at": r[6].isoformat() if r[6] else None,
                        "is_read": r[6] is not None
                    }
                    for r in rows
                ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/v1/alerts/{alert_id}/read")
def mark_alert_read(alert_id: int, user: dict = Depends(get_current_user)):
    """Mark an alert as read"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE notifications SET read_at = NOW() WHERE id = %s AND user_id = %s",
                    (alert_id, user["id"])
                )
                conn.commit()
        return {"status": "marked_read"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/v1/alerts/read-all")
def mark_all_alerts_read(user: dict = Depends(get_current_user)):
    """Mark all alerts as read"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE notifications SET read_at = NOW() WHERE user_id = %s AND read_at IS NULL",
                    (user["id"],)
                )
                conn.commit()
        return {"status": "all_marked_read"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===================== EMERGENCY CONTACTS ENDPOINTS =====================

@app.get("/api/v1/emergency-contacts")
def get_emergency_contacts(user: dict = Depends(get_current_user)):
    """Get emergency contacts for authenticated user"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, name, phone, relationship, is_primary 
                    FROM emergency_contacts 
                    WHERE user_id = %s 
                    ORDER BY is_primary DESC, name ASC
                """, (user["id"],))
                rows = cur.fetchall()
                return [
                    {"id": r[0], "name": r[1], "phone": r[2], "relationship": r[3], "is_primary": r[4]}
                    for r in rows
                ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/emergency-contacts")
def add_emergency_contact(contact: EmergencyContact, user: dict = Depends(get_current_user)):
    """Add an emergency contact"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if contact.is_primary:
                    cur.execute(
                        "UPDATE emergency_contacts SET is_primary = FALSE WHERE user_id = %s",
                        (user["id"],)
                    )
                
                cur.execute("""
                    INSERT INTO emergency_contacts (user_id, name, phone, relationship, is_primary)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id
                """, (user["id"], contact.name, contact.phone, contact.relationship, contact.is_primary))
                contact_id = cur.fetchone()[0]
                conn.commit()
                
        return {"id": contact_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/v1/emergency-contacts/{contact_id}")
def update_emergency_contact(contact_id: int, contact: EmergencyContact, user: dict = Depends(get_current_user)):
    """Update an emergency contact"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if contact.is_primary:
                    cur.execute(
                        "UPDATE emergency_contacts SET is_primary = FALSE WHERE user_id = %s",
                        (user["id"],)
                    )
                
                cur.execute("""
                    UPDATE emergency_contacts 
                    SET name = %s, phone = %s, relationship = %s, is_primary = %s
                    WHERE id = %s AND user_id = %s
                """, (contact.name, contact.phone, contact.relationship, contact.is_primary, contact_id, user["id"]))
                conn.commit()
                
        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/emergency-contacts/{contact_id}")
def delete_emergency_contact(contact_id: int, user: dict = Depends(get_current_user)):
    """Delete an emergency contact"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM emergency_contacts WHERE id = %s AND user_id = %s",
                    (contact_id, user["id"])
                )
                conn.commit()
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===================== USER SETTINGS ENDPOINTS =====================

@app.get("/api/v1/settings")
def get_user_settings(user: dict = Depends(get_current_user)):
    """Get user settings"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT low_spo2_threshold, high_hr_threshold, low_hr_threshold,
                           enable_predictive_alerts, enable_anomaly_alerts, enable_emergency_alerts,
                           enable_sound, enable_vibration
                    FROM user_settings WHERE user_id = %s
                """, (user["id"],))
                row = cur.fetchone()
                if not row:
                    return UserSettings().dict()
                
                return {
                    "low_spo2_threshold": row[0],
                    "high_hr_threshold": row[1],
                    "low_hr_threshold": row[2],
                    "enable_predictive_alerts": row[3],
                    "enable_anomaly_alerts": row[4],
                    "enable_emergency_alerts": row[5],
                    "enable_sound": row[6],
                    "enable_vibration": row[7]
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/v1/settings")
def update_user_settings(settings: UserSettings, user: dict = Depends(get_current_user)):
    """Update user settings"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO user_settings (user_id, low_spo2_threshold, high_hr_threshold, low_hr_threshold,
                        enable_predictive_alerts, enable_anomaly_alerts, enable_emergency_alerts,
                        enable_sound, enable_vibration, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (user_id) DO UPDATE SET
                        low_spo2_threshold = EXCLUDED.low_spo2_threshold,
                        high_hr_threshold = EXCLUDED.high_hr_threshold,
                        low_hr_threshold = EXCLUDED.low_hr_threshold,
                        enable_predictive_alerts = EXCLUDED.enable_predictive_alerts,
                        enable_anomaly_alerts = EXCLUDED.enable_anomaly_alerts,
                        enable_emergency_alerts = EXCLUDED.enable_emergency_alerts,
                        enable_sound = EXCLUDED.enable_sound,
                        enable_vibration = EXCLUDED.enable_vibration,
                        updated_at = NOW()
                """, (
                    user["id"], settings.low_spo2_threshold, settings.high_hr_threshold,
                    settings.low_hr_threshold, settings.enable_predictive_alerts,
                    settings.enable_anomaly_alerts, settings.enable_emergency_alerts,
                    settings.enable_sound, settings.enable_vibration
                ))
                conn.commit()
        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===================== WEBSOCKET ENDPOINT =====================

@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    """WebSocket for real-time health data streaming"""
    await manager.connect(websocket, device_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(device_id)

# ===================== PUSH NOTIFICATION HELPERS =====================

async def send_push_notification(user_id: int, device_id: str, title: str, body: str, 
                                  notification_type: str, data: dict = None):
    """Send push notification to user/device"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO notifications (device_id, user_id, notification_type, title, body, data)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (device_id, user_id, notification_type, title, body, json.dumps(data or {})))
                conn.commit()
                
                if FIREBASE_ENABLED:
                    cur.execute("SELECT fcm_token FROM devices WHERE device_id = %s", (device_id,))
                    row = cur.fetchone()
                    if row and row[0]:
                        message = messaging.Message(
                            notification=messaging.Notification(title=title, body=body),
                            data={"type": notification_type, **(data or {})},
                            token=row[0],
                        )
                        messaging.send(message)
        
        await manager.send_to_device(device_id, {
            "type": "notification",
            "notification_type": notification_type,
            "title": title,
            "body": body,
            "data": data
        })
        
        return True
    except Exception as e:
        logging.error(f"Push notification failed: {e}")
        return False

# ===================== BACKGROUND WORKERS =====================

def prediction_worker():
    logging.info("Prediction worker started...")
    while True:
        try:
            with get_db_connection() as conn:
                processed_snapshot = process_snapshot_models(conn)
                processed_forecast = process_forecasting_models(conn)
                if not processed_snapshot and not processed_forecast:
                    time.sleep(5)
                else:
                    time.sleep(1)
        except Exception as e:
            logging.error(f"Error in prediction worker: {e}")
            time.sleep(10)


def process_snapshot_models(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT time, device_id FROM smartwatch_readings WHERE prediction IS NULL OR is_anomaly IS NULL ORDER BY time ASC LIMIT 1")
        row = cur.fetchone()
        if not row:
            return False
        current_time, device_id = row[0], row[1]
        logging.info(f"Processing snapshot for: {current_time}")
        cur.execute(
            "SELECT heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z, COALESCE(LAG(heart_rate, 1) OVER (ORDER BY time), heart_rate) as prev_hr, COALESCE(LAG(spo2, 1) OVER (ORDER BY time), spo2) as prev_spo2 FROM smartwatch_readings WHERE time <= %s ORDER BY time DESC LIMIT 2",
            (current_time,))
        readings = cur.fetchall()
        current_reading, prev_reading = readings[0], readings[-1]
        payload = {"heart_rate": current_reading[0], "spo2": current_reading[1], "accel_x": current_reading[2],
                   "accel_y": current_reading[3], "accel_z": current_reading[4], "gyro_x": current_reading[5],
                   "gyro_y": current_reading[6], "gyro_z": current_reading[7], "previous_heart_rate": prev_reading[0],
                   "previous_spo2": prev_reading[1]}
        class_res, anomaly_res = requests.post(CLASSIFICATION_API_URL, json=payload), requests.post(ANOMALY_API_URL, json=payload)
        if class_res.status_code == 200 and anomaly_res.status_code == 200:
            class_data, anomaly_data = class_res.json(), anomaly_res.json()
            features = class_data.get("engineered_features", {})
            with conn.cursor() as update_cur:
                update_sql = "UPDATE smartwatch_readings SET prediction = %s, is_anomaly = %s, hr_diff = %s, spo2_diff = %s, stress_index = %s, hr_spo2_ratio = %s, accel_mag = %s, gyro_mag = %s WHERE time = %s"
                update_cur.execute(update_sql, (class_data.get("prediction"), anomaly_data.get("is_anomaly"),
                                                features.get('hr_diff'), features.get('spo2_diff'),
                                                features.get('stress_index'), features.get('hr_spo2_ratio'),
                                                features.get('accel_mag'), features.get('gyro_mag'), current_time))
            conn.commit()
            logging.info(f"Updated snapshot for {current_time} -> Pred: {class_data.get('prediction')}, Anomaly: {anomaly_data.get('is_anomaly')}")
            
            prediction = class_data.get("prediction")
            is_anomaly = anomaly_data.get("is_anomaly")
            
            if device_id and (is_anomaly or prediction in ["Tachycardia", "Bradycardia", "Arrhythmia", "Hypoxia"]):
                cur.execute("SELECT user_id FROM devices WHERE device_id = %s", (device_id,))
                user_row = cur.fetchone()
                if user_row:
                    user_id = user_row[0]
                    
                    cur.execute("SELECT enable_anomaly_alerts, enable_emergency_alerts FROM user_settings WHERE user_id = %s", (user_id,))
                    settings_row = cur.fetchone()
                    enable_anomaly = settings_row[0] if settings_row else True
                    enable_emergency = settings_row[1] if settings_row else True
                    
                    if is_anomaly and enable_anomaly:
                        cur.execute("""
                            INSERT INTO notifications (device_id, user_id, notification_type, title, body, data)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                            device_id, user_id, "anomaly",
                            "⚠️ Health Anomaly Detected",
                            f"Unusual reading detected. HR: {current_reading[0]:.0f}, SpO2: {current_reading[1]:.0f}%",
                            json.dumps({"heart_rate": current_reading[0], "spo2": current_reading[1]})
                        ))
                        conn.commit()
                        logging.info(f"Anomaly notification created for user {user_id}")
                    
                    if prediction in ["Tachycardia", "Bradycardia", "Arrhythmia", "Hypoxia"] and enable_emergency:
                        cur.execute("""
                            INSERT INTO notifications (device_id, user_id, notification_type, title, body, data)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                            device_id, user_id, "critical",
                            "🚨 Critical Health Alert",
                            f"Condition detected: {prediction}. Please check your vitals.",
                            json.dumps({"prediction": prediction})
                        ))
                        conn.commit()
                        logging.info(f"Critical notification created for user {user_id}: {prediction}")
            
            return True
        else:
            logging.error(f"Snapshot API failed. Class: {class_res.status_code}, Anomaly: {anomaly_res.status_code}")
            return False


def process_forecasting_models(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM smartwatch_readings;")
        total_rows = cur.fetchone()[0]
        if total_rows < LOOKBACK_WINDOW:
            return False
        cur.execute(
            "WITH RankedRows AS (SELECT time, ROW_NUMBER() OVER (ORDER BY time ASC) as rn FROM smartwatch_readings) SELECT rr.time FROM RankedRows rr JOIN smartwatch_readings sr ON rr.time = sr.time WHERE sr.forecasted_prediction IS NULL AND rr.rn >= %s ORDER BY rr.time ASC LIMIT 1;",
            (LOOKBACK_WINDOW,))
        row = cur.fetchone()
        if not row:
            return False
        current_time = row[0]
        logging.info(f"Processing forecast for: {current_time}")
        cur.execute(
            "SELECT heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z, COALESCE(LAG(heart_rate, 1) OVER (ORDER BY time), heart_rate) as prev_hr, COALESCE(LAG(spo2, 1) OVER (ORDER BY time), spo2) as prev_spo2 FROM smartwatch_readings WHERE time <= %s ORDER BY time DESC LIMIT %s",
            (current_time, LOOKBACK_WINDOW))
        sequence_rows = cur.fetchall()
        if len(sequence_rows) < LOOKBACK_WINDOW:
            logging.warning(f"Not enough history for {current_time}.")
            return False
        sequence_rows.reverse()
        payload_sequence = [
            {"heart_rate": r[0], "spo2": r[1], "accel_x": r[2], "accel_y": r[3], "accel_z": r[4], "gyro_x": r[5],
             "gyro_y": r[6], "gyro_z": r[7], "previous_heart_rate": r[8], "previous_spo2": r[9]} for r in sequence_rows]
        forecast_res = requests.post(FORECASTING_API_URL, json={"sequence": payload_sequence})
        if forecast_res.status_code == 200:
            forecast_data = forecast_res.json()
            with conn.cursor() as update_cur:
                update_cur.execute("UPDATE smartwatch_readings SET forecasted_prediction = %s WHERE time = %s",
                                   (forecast_data.get("forecasted_prediction"), current_time))
            conn.commit()
            logging.info(f"Updated forecast for {current_time} -> Forecast: {forecast_data.get('forecasted_prediction')}")
            return True
        else:
            logging.error(f"Forecast API failed for {current_time}: {forecast_res.status_code} - {forecast_res.text}")
            return False


def clustering_worker():
    if not all([dbscan_model, dbscan_scaler]):
        logging.warning("Clustering worker disabled.")
        return
    logging.info("Clustering worker started...")
    while True:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    logging.info("Running clustering job.")
                    cur.execute(
                        "SELECT time, heart_rate, spo2, hr_diff, spo2_diff, stress_index, hr_spo2_ratio, accel_mag, gyro_mag FROM smartwatch_readings WHERE cluster_id IS NULL AND accel_mag IS NOT NULL")
                    rows = cur.fetchall()
                    if rows:
                        logging.info(f"Found {len(rows)} rows to cluster.")
                        df = pd.DataFrame(rows,
                                          columns=['time', 'heart_rate', 'spo2', 'hr_diff', 'spo2_diff', 'stress_index',
                                                   'hr_spo2_ratio', 'accel_mag', 'gyro_mag'])
                        features = df.columns.drop('time')
                        X_scaled = dbscan_scaler.transform(df[features])
                        clusters = dbscan_model.fit_predict(X_scaled)
                        for index, row in enumerate(df.itertuples()):
                            cluster_id = int(clusters[index])
                            cluster_label = CLUSTER_NAME_MAP.get(cluster_id, "Unknown")
                            with conn.cursor() as update_cur:
                                update_cur.execute(
                                    "UPDATE smartwatch_readings SET cluster_id = %s, cluster_label = %s WHERE time = %s",
                                    (cluster_id, cluster_label, row.time))
                        conn.commit()
                        logging.info(f"Updated cluster IDs for {len(rows)} rows.")
                    else:
                        logging.info("No new rows to cluster.")
        except Exception as e:
            logging.error(f"Error in clustering worker: {e}")
        logging.info(f"Clustering job finished. Next run in {CLUSTERING_INTERVAL_SECONDS / 3600} hours.")
        time.sleep(CLUSTERING_INTERVAL_SECONDS)


def health_summary_worker():
    logging.info("Health summary worker started...")
    while True:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    logging.info("Running scheduled health summary and trend analysis job.")
                    cur.execute(
                        "SELECT AVG(heart_rate) FROM smartwatch_readings WHERE time >= NOW() - INTERVAL '7 days' AND accel_mag < 10.5;")
                    avg_hr_current = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COUNT(*) * 2 FROM smartwatch_readings WHERE time >= NOW() - INTERVAL '7 days' AND prediction IN ('Stressed', 'Tachycardia');")
                    minutes_stressed = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COUNT(*) * 2 FROM smartwatch_readings WHERE time >= NOW() - INTERVAL '7 days' AND prediction = 'Exercising';")
                    minutes_exercising = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COUNT(*) FROM smartwatch_readings WHERE time >= NOW() - INTERVAL '7 days' AND is_anomaly = TRUE;")
                    anomaly_count = cur.fetchone()[0]
                    cur.execute(
                        "SELECT AVG(heart_rate) FROM smartwatch_readings WHERE time >= NOW() - INTERVAL '14 days' AND time < NOW() - INTERVAL '7 days' AND accel_mag < 10.5;")
                    avg_hr_previous = cur.fetchone()[0]
                    hr_trend = 0.0
                    if avg_hr_current is not None and avg_hr_previous is not None:
                        hr_trend = avg_hr_current - avg_hr_previous
                    insert_sql = """
                        INSERT INTO health_summaries (summary_date, avg_resting_hr, minutes_in_stress, minutes_exercising, total_anomalies, resting_hr_weekly_change)
                        VALUES (CURRENT_DATE, %s, %s, %s, %s, %s)
                        ON CONFLICT (summary_date) DO UPDATE SET
                            avg_resting_hr = EXCLUDED.avg_resting_hr,
                            minutes_in_stress = EXCLUDED.minutes_in_stress,
                            minutes_exercising = EXCLUDED.minutes_exercising,
                            total_anomalies = EXCLUDED.total_anomalies,
                            resting_hr_weekly_change = EXCLUDED.resting_hr_weekly_change;
                    """
                    cur.execute(insert_sql,
                                (avg_hr_current, minutes_stressed, minutes_exercising, anomaly_count, hr_trend))
                    conn.commit()
                    logging.info(
                        f"Health summary for {datetime.now().date()} saved successfully. Weekly HR trend: {hr_trend:+.1f} bpm.")
        except Exception as e:
            logging.error(f"An error occurred in the health summary worker: {e}")
        logging.info(f"Health summary job finished. Next run in {SUMMARY_INTERVAL_SECONDS / 3600} hours.")
        time.sleep(SUMMARY_INTERVAL_SECONDS)


@app.on_event("startup")
def startup_event():
    prediction_thread = threading.Thread(target=prediction_worker, daemon=True)
    clustering_thread = threading.Thread(target=clustering_worker, daemon=True)
    summary_thread = threading.Thread(target=health_summary_worker, daemon=True)
    prediction_thread.start()
    clustering_thread.start()
    summary_thread.start()
