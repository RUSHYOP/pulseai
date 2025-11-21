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

# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
DB_HOST = "db";
DB_NAME = os.getenv("POSTGRES_DB");
DB_USER = os.getenv("POSTGRES_USER");
DB_PASS = os.getenv("POSTGRES_PASSWORD")
CLASSIFICATION_API_URL = "http://ml-api:8000/predict_classification"
ANOMALY_API_URL = "http://ml-api:8000/predict_anomaly"
FORECASTING_API_URL = "http://ml-api:8000/forecast_risk"
LOOKBACK_WINDOW = 30
CLUSTERING_INTERVAL_SECONDS = 3600
SUMMARY_INTERVAL_SECONDS = 86400  # Run summary analysis once every 24 hours

# (Model Loading, FastAPI app setup, and other configurations remain the same)
try:
    dbscan_model = joblib.load("dbscan_model.pkl");
    dbscan_scaler = joblib.load("dbscan_scaler.pkl")
    logging.info("✅ DBSCAN model and scaler loaded.")
except FileNotFoundError:
    dbscan_model, dbscan_scaler = None, None
    logging.warning("⚠️ DBSCAN models not found. Clustering disabled.")

app = FastAPI(title="Data Ingestion, Processing & Analysis Service")


class RawSensorData(BaseModel):
    heart_rate: float;
    spo2: float;
    accel_x: float;
    accel_y: float;
    accel_z: float;
    gyro_x: float;
    gyro_y: float;
    gyro_z: float


CLUSTER_NAME_MAP = {-1: "Noise/Undefined", 0: "Resting", 1: "Light Activity", 2: "Moderate Activity", 3: "Commuting"}


def get_db_connection():
    if not all([DB_NAME, DB_USER, DB_PASS]): raise ConnectionError("Missing DB credentials")
    return psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS)


# (/ingest and /summary endpoints remain the same as the previous version)
@app.post("/ingest")
def ingest_data(reading: RawSensorData):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                sql = "INSERT INTO smartwatch_readings (heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                cur.execute(sql, (reading.heart_rate, reading.spo2, reading.accel_x, reading.accel_y, reading.accel_z,
                                  reading.gyro_x, reading.gyro_y, reading.gyro_z))
                conn.commit()
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Ingestion failed: {e}");
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/summary")
def get_daily_summary():
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
                avg_hr = cur.fetchone()[0];
                summary['average_resting_hr'] = round(avg_hr, 1) if avg_hr else None
                cur.execute(
                    "SELECT cluster_label, COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () FROM smartwatch_readings WHERE time >= NOW() - INTERVAL '24 hours' AND cluster_label IS NOT NULL AND cluster_label != 'Noise/Undefined' GROUP BY cluster_label;")
                summary['activity_distribution_percent'] = {label: round(percent, 2) for label, percent in
                                                            cur.fetchall()}
        return summary
    except Exception as e:
        logging.error(f"Summary generation failed: {e}");
        raise HTTPException(status_code=500, detail=f"Could not generate summary: {e}")


# --- NEW: Trend Analysis Endpoint ---
@app.get("/summary/trends")
def get_health_trends():
    """
    Retrieves the last 30 days of generated health summaries for trend analysis.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM health_summaries ORDER BY summary_date DESC LIMIT 30")
                trends = cur.fetchall()
                # Format the results into a more frontend-friendly list of objects
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in trends]
    except Exception as e:
        logging.error(f"Trend retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Could not retrieve trends: {e}")


# --- Background Workers ---
# (prediction_worker and clustering_worker and their helpers remain unchanged)
def prediction_worker():
    logging.info("Prediction worker started...")
    while True:
        try:
            with get_db_connection() as conn:
                processed_snapshot = process_snapshot_models(conn);
                processed_forecast = process_forecasting_models(conn)
                if not processed_snapshot and not processed_forecast:
                    time.sleep(5)
                else:
                    time.sleep(1)
        except Exception as e:
            logging.error(f"Error in prediction worker: {e}");
            time.sleep(10)


def process_snapshot_models(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT time FROM smartwatch_readings WHERE prediction IS NULL OR is_anomaly IS NULL ORDER BY time ASC LIMIT 1");
        row = cur.fetchone()
        if not row: return False
        current_time = row[0];
        logging.info(f"Processing snapshot for: {current_time}")
        cur.execute(
            "SELECT heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z, COALESCE(LAG(heart_rate, 1) OVER (ORDER BY time), heart_rate) as prev_hr, COALESCE(LAG(spo2, 1) OVER (ORDER BY time), spo2) as prev_spo2 FROM smartwatch_readings WHERE time <= %s ORDER BY time DESC LIMIT 2",
            (current_time,));
        readings = cur.fetchall();
        current_reading, prev_reading = readings[0], readings[-1]
        payload = {"heart_rate": current_reading[0], "spo2": current_reading[1], "accel_x": current_reading[2],
                   "accel_y": current_reading[3], "accel_z": current_reading[4], "gyro_x": current_reading[5],
                   "gyro_y": current_reading[6], "gyro_z": current_reading[7], "previous_heart_rate": prev_reading[0],
                   "previous_spo2": prev_reading[1]}
        class_res, anomaly_res = requests.post(CLASSIFICATION_API_URL, json=payload), requests.post(ANOMALY_API_URL,
                                                                                                    json=payload)
        if class_res.status_code == 200 and anomaly_res.status_code == 200:
            class_data, anomaly_data = class_res.json(), anomaly_res.json();
            features = class_data.get("engineered_features", {})
            with conn.cursor() as update_cur:
                update_sql = "UPDATE smartwatch_readings SET prediction = %s, is_anomaly = %s, hr_diff = %s, spo2_diff = %s, stress_index = %s, hr_spo2_ratio = %s, accel_mag = %s, gyro_mag = %s WHERE time = %s"
                update_cur.execute(update_sql, (class_data.get("prediction"), anomaly_data.get("is_anomaly"),
                                                features.get('hr_diff'), features.get('spo2_diff'),
                                                features.get('stress_index'), features.get('hr_spo2_ratio'),
                                                features.get('accel_mag'), features.get('gyro_mag'), current_time))
            conn.commit();
            logging.info(
                f"Updated snapshot for {current_time} -> Pred: {class_data.get('prediction')}, Anomaly: {anomaly_data.get('is_anomaly')}");
            return True
        else:
            logging.error(f"Snapshot API failed. Class: {class_res.status_code}, Anomaly: {anomaly_res.status_code}");
            return False


def process_forecasting_models(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM smartwatch_readings;");
        total_rows = cur.fetchone()[0]
        if total_rows < LOOKBACK_WINDOW: return False
        cur.execute(
            "WITH RankedRows AS (SELECT time, ROW_NUMBER() OVER (ORDER BY time ASC) as rn FROM smartwatch_readings) SELECT rr.time FROM RankedRows rr JOIN smartwatch_readings sr ON rr.time = sr.time WHERE sr.forecasted_prediction IS NULL AND rr.rn >= %s ORDER BY rr.time ASC LIMIT 1;",
            (LOOKBACK_WINDOW,));
        row = cur.fetchone()
        if not row: return False
        current_time = row[0];
        logging.info(f"Processing forecast for: {current_time}")
        cur.execute(
            "SELECT heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z, COALESCE(LAG(heart_rate, 1) OVER (ORDER BY time), heart_rate) as prev_hr, COALESCE(LAG(spo2, 1) OVER (ORDER BY time), spo2) as prev_spo2 FROM smartwatch_readings WHERE time <= %s ORDER BY time DESC LIMIT %s",
            (current_time, LOOKBACK_WINDOW));
        sequence_rows = cur.fetchall()
        if len(sequence_rows) < LOOKBACK_WINDOW: logging.warning(
            f"Not enough history for {current_time}."); return False
        sequence_rows.reverse();
        payload_sequence = [
            {"heart_rate": r[0], "spo2": r[1], "accel_x": r[2], "accel_y": r[3], "accel_z": r[4], "gyro_x": r[5],
             "gyro_y": r[6], "gyro_z": r[7], "previous_heart_rate": r[8], "previous_spo2": r[9]} for r in sequence_rows]
        forecast_res = requests.post(FORECASTING_API_URL, json={"sequence": payload_sequence})
        if forecast_res.status_code == 200:
            forecast_data = forecast_res.json()
            with conn.cursor() as update_cur:
                update_cur.execute("UPDATE smartwatch_readings SET forecasted_prediction = %s WHERE time = %s",
                                   (forecast_data.get("forecasted_prediction"), current_time))
            conn.commit();
            logging.info(
                f"Updated forecast for {current_time} -> Forecast: {forecast_data.get('forecasted_prediction')}");
            return True
        else:
            logging.error(f"Forecast API failed for {current_time}: {forecast_res.status_code} - {forecast_res.text}");
            return False


def clustering_worker():
    if not all([dbscan_model, dbscan_scaler]): logging.warning("Clustering worker disabled."); return
    logging.info("Clustering worker started...")
    while True:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    logging.info("Running clustering job.");
                    cur.execute(
                        "SELECT time, heart_rate, spo2, hr_diff, spo2_diff, stress_index, hr_spo2_ratio, accel_mag, gyro_mag FROM smartwatch_readings WHERE cluster_id IS NULL AND accel_mag IS NOT NULL");
                    rows = cur.fetchall()
                    if rows:
                        logging.info(f"Found {len(rows)} rows to cluster.")
                        df = pd.DataFrame(rows,
                                          columns=['time', 'heart_rate', 'spo2', 'hr_diff', 'spo2_diff', 'stress_index',
                                                   'hr_spo2_ratio', 'accel_mag', 'gyro_mag']);
                        features = df.columns.drop('time')
                        X_scaled = dbscan_scaler.transform(df[features]);
                        clusters = dbscan_model.fit_predict(X_scaled)
                        for index, row in enumerate(df.itertuples()):
                            cluster_id = int(clusters[index]);
                            cluster_label = CLUSTER_NAME_MAP.get(cluster_id, "Unknown")
                            with conn.cursor() as update_cur:
                                update_cur.execute(
                                    "UPDATE smartwatch_readings SET cluster_id = %s, cluster_label = %s WHERE time = %s",
                                    (cluster_id, cluster_label, row.time))
                        conn.commit();
                        logging.info(f"Updated cluster IDs for {len(rows)} rows.")
                    else:
                        logging.info("No new rows to cluster.")
        except Exception as e:
            logging.error(f"Error in clustering worker: {e}")
        logging.info(f"Clustering job finished. Next run in {CLUSTERING_INTERVAL_SECONDS / 3600} hours.");
        time.sleep(CLUSTERING_INTERVAL_SECONDS)


# --- NEW: Health Summary and Trend Analysis Worker ---
def health_summary_worker():
    logging.info("Health summary worker started...")
    while True:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    logging.info("Running scheduled health summary and trend analysis job.")

                    # 1. Calculate this week's metrics
                    cur.execute(
                        "SELECT AVG(heart_rate) FROM smartwatch_readings WHERE time >= NOW() - INTERVAL '7 days' AND accel_mag < 10.5;");
                    avg_hr_current = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COUNT(*) * 2 FROM smartwatch_readings WHERE time >= NOW() - INTERVAL '7 days' AND prediction IN ('Stressed', 'Tachycardia');");
                    minutes_stressed = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COUNT(*) * 2 FROM smartwatch_readings WHERE time >= NOW() - INTERVAL '7 days' AND prediction = 'Exercising';");
                    minutes_exercising = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COUNT(*) FROM smartwatch_readings WHERE time >= NOW() - INTERVAL '7 days' AND is_anomaly = TRUE;");
                    anomaly_count = cur.fetchone()[0]

                    # 2. Calculate trend by comparing to the previous week
                    cur.execute(
                        "SELECT AVG(heart_rate) FROM smartwatch_readings WHERE time >= NOW() - INTERVAL '14 days' AND time < NOW() - INTERVAL '7 days' AND accel_mag < 10.5;");
                    avg_hr_previous = cur.fetchone()[0]

                    hr_trend = 0.0
                    if avg_hr_current is not None and avg_hr_previous is not None:
                        hr_trend = avg_hr_current - avg_hr_previous

                    # 3. Save to the health_summaries table
                    # Using ON CONFLICT to either INSERT a new row or UPDATE the existing one for today's date
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

        logging.info(f"Health summary job finished. Next run in {SUMMARY_INTERVAL_SECONDS / 3600} hours.");
        time.sleep(SUMMARY_INTERVAL_SECONDS)


@app.on_event("startup")
def startup_event():
    # Start all three background workers
    prediction_thread = threading.Thread(target=prediction_worker, daemon=True)
    clustering_thread = threading.Thread(target=clustering_worker, daemon=True)
    summary_thread = threading.Thread(target=health_summary_worker, daemon=True)

    prediction_thread.start()
    clustering_thread.start()
    summary_thread.start()


