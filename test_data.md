# Test Data for PulsAI

## Quick Insert Commands

SSH into the server first:
```bash
ssh -i "newkey.pem" rushy@34.197.138.31
docker exec -it timescaledb psql -U rushy -d readings
```

---

## Single Record Inserts

### Normal Reading
```sql
INSERT INTO smartwatch_readings (device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z)
VALUES ('001A', 72.0, 98.0, 0.1, 0.2, 9.8, 0.01, 0.02, 0.01);
```

### Resting (Low Activity)
```sql
INSERT INTO smartwatch_readings (device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z)
VALUES ('001A', 62.0, 99.0, 0.05, 0.08, 9.81, 0.005, 0.008, 0.003);
```

### Exercising (High Activity)
```sql
-- High HR + High motion = Exercise (accel_mag ~15-18, gyro_mag ~2-3)
INSERT INTO smartwatch_readings (device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z)
VALUES ('001A', 135.0, 95.0, 8.5, 10.2, 12.0, 1.8, 2.2, 1.5);
```

### Tachycardia (High HR)
```sql
-- High HR + LOW motion = Tachycardia (accel_mag ~9.8, minimal gyro)
INSERT INTO smartwatch_readings (device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z)
VALUES ('001A', 150.0, 97.0, 0.1, 0.2, 9.8, 0.01, 0.02, 0.01);
```

### Bradycardia (Low HR)
```sql
INSERT INTO smartwatch_readings (device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z)
VALUES ('001A', 45.0, 98.0, 0.1, 0.15, 9.8, 0.01, 0.01, 0.01);
```

### Hypoxia (Low SpO2)
```sql
INSERT INTO smartwatch_readings (device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z)
VALUES ('001A', 88.0, 85.0, 0.2, 0.3, 9.8, 0.02, 0.03, 0.01);
```

### Stressed
```sql
INSERT INTO smartwatch_readings (device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z)
VALUES ('001A', 105.0, 95.0, 0.5, 0.6, 10.2, 0.1, 0.15, 0.08);
```

### Anomaly (Unusual Pattern)
```sql
INSERT INTO smartwatch_readings (device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z)
VALUES ('001A', 180.0, 82.0, 0.1, 0.2, 9.8, 0.01, 0.02, 0.01);
```

---

## Bulk Insert - Mixed Data (50 Records)

```sql
INSERT INTO smartwatch_readings (device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z) VALUES
-- Normal readings (cluster 0 - Resting)
('001A', 68.0, 98.0, 0.08, 0.12, 9.81, 0.01, 0.01, 0.01),
('001A', 70.0, 99.0, 0.05, 0.10, 9.80, 0.008, 0.012, 0.005),
('001A', 65.0, 98.5, 0.10, 0.08, 9.82, 0.012, 0.008, 0.006),
('001A', 72.0, 97.5, 0.06, 0.09, 9.79, 0.009, 0.011, 0.007),
('001A', 69.0, 98.0, 0.07, 0.11, 9.81, 0.010, 0.010, 0.008),
('001A', 67.0, 99.0, 0.04, 0.06, 9.80, 0.006, 0.007, 0.004),
('001A', 71.0, 98.0, 0.09, 0.13, 9.82, 0.011, 0.013, 0.009),
('001A', 66.0, 98.5, 0.05, 0.07, 9.81, 0.007, 0.009, 0.005),
('001A', 73.0, 97.0, 0.08, 0.10, 9.79, 0.010, 0.012, 0.008),
('001A', 64.0, 99.0, 0.03, 0.05, 9.80, 0.005, 0.006, 0.003),

-- Light Activity (cluster 1)
('001A', 82.0, 97.0, 0.8, 1.2, 10.5, 0.15, 0.20, 0.10),
('001A', 85.0, 96.5, 1.0, 1.5, 10.8, 0.18, 0.25, 0.12),
('001A', 88.0, 96.0, 1.2, 1.8, 11.0, 0.22, 0.30, 0.15),
('001A', 80.0, 97.5, 0.6, 0.9, 10.3, 0.12, 0.18, 0.08),
('001A', 84.0, 97.0, 0.9, 1.3, 10.6, 0.16, 0.22, 0.11),
('001A', 86.0, 96.5, 1.1, 1.6, 10.9, 0.20, 0.28, 0.14),
('001A', 83.0, 97.0, 0.7, 1.1, 10.4, 0.14, 0.19, 0.09),
('001A', 87.0, 96.0, 1.3, 1.9, 11.2, 0.24, 0.32, 0.16),
('001A', 81.0, 97.5, 0.5, 0.8, 10.2, 0.11, 0.16, 0.07),
('001A', 89.0, 96.0, 1.4, 2.0, 11.3, 0.26, 0.35, 0.18),

-- Moderate Activity / Exercise (cluster 2)
('001A', 115.0, 95.0, 2.5, 3.5, 13.0, 0.8, 1.0, 0.5),
('001A', 120.0, 94.5, 3.0, 4.0, 13.5, 0.9, 1.2, 0.6),
('001A', 125.0, 94.0, 3.5, 4.5, 14.0, 1.0, 1.4, 0.7),
('001A', 130.0, 93.5, 4.0, 5.0, 14.5, 1.1, 1.6, 0.8),
('001A', 118.0, 95.0, 2.8, 3.8, 13.2, 0.85, 1.1, 0.55),
('001A', 122.0, 94.5, 3.2, 4.2, 13.8, 0.95, 1.3, 0.65),
('001A', 128.0, 94.0, 3.8, 4.8, 14.2, 1.05, 1.5, 0.75),
('001A', 135.0, 93.0, 4.5, 5.5, 15.0, 1.2, 1.8, 0.9),
('001A', 112.0, 95.5, 2.2, 3.2, 12.5, 0.7, 0.9, 0.45),
('001A', 140.0, 92.5, 5.0, 6.0, 15.5, 1.3, 2.0, 1.0),

-- Tachycardia cases
('001A', 152.0, 96.0, 0.2, 0.3, 9.9, 0.02, 0.03, 0.02),
('001A', 158.0, 95.5, 0.3, 0.4, 10.0, 0.03, 0.04, 0.02),
('001A', 148.0, 96.5, 0.15, 0.25, 9.85, 0.018, 0.025, 0.015),
('001A', 155.0, 96.0, 0.25, 0.35, 9.95, 0.025, 0.035, 0.018),
('001A', 162.0, 95.0, 0.35, 0.45, 10.1, 0.035, 0.045, 0.025),

-- Bradycardia cases
('001A', 48.0, 98.0, 0.05, 0.08, 9.8, 0.005, 0.008, 0.004),
('001A', 45.0, 98.5, 0.04, 0.06, 9.81, 0.004, 0.006, 0.003),
('001A', 52.0, 97.5, 0.06, 0.09, 9.79, 0.006, 0.009, 0.005),
('001A', 42.0, 99.0, 0.03, 0.05, 9.82, 0.003, 0.005, 0.002),
('001A', 55.0, 97.0, 0.07, 0.10, 9.78, 0.007, 0.010, 0.006),

-- Hypoxia cases
('001A', 92.0, 88.0, 0.2, 0.3, 9.9, 0.02, 0.03, 0.02),
('001A', 95.0, 85.0, 0.25, 0.35, 9.95, 0.025, 0.035, 0.025),
('001A', 88.0, 89.0, 0.15, 0.25, 9.85, 0.015, 0.025, 0.015),
('001A', 98.0, 84.0, 0.3, 0.4, 10.0, 0.03, 0.04, 0.03),
('001A', 90.0, 87.0, 0.18, 0.28, 9.88, 0.018, 0.028, 0.018),

-- Stressed readings
('001A', 102.0, 95.0, 0.5, 0.7, 10.2, 0.08, 0.12, 0.06),
('001A', 108.0, 94.5, 0.6, 0.8, 10.4, 0.10, 0.15, 0.08),
('001A', 105.0, 95.0, 0.55, 0.75, 10.3, 0.09, 0.13, 0.07),
('001A', 110.0, 94.0, 0.7, 0.9, 10.5, 0.12, 0.18, 0.10),
('001A', 100.0, 95.5, 0.45, 0.65, 10.1, 0.07, 0.11, 0.05);
```

---

## Time-Series Data (Simulating 24 Hours)

```sql
-- Insert data with timestamps spread over 24 hours
INSERT INTO smartwatch_readings (time, device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z) VALUES
-- Night (sleeping - low HR, resting)
(NOW() - INTERVAL '23 hours', '001A', 58.0, 99.0, 0.02, 0.03, 9.81, 0.002, 0.003, 0.001),
(NOW() - INTERVAL '22 hours', '001A', 56.0, 99.0, 0.01, 0.02, 9.80, 0.001, 0.002, 0.001),
(NOW() - INTERVAL '21 hours', '001A', 55.0, 99.0, 0.02, 0.02, 9.81, 0.002, 0.002, 0.001),
(NOW() - INTERVAL '20 hours', '001A', 57.0, 99.0, 0.03, 0.03, 9.80, 0.003, 0.003, 0.002),

-- Morning wake up
(NOW() - INTERVAL '19 hours', '001A', 62.0, 98.5, 0.5, 0.6, 10.0, 0.05, 0.06, 0.03),
(NOW() - INTERVAL '18 hours', '001A', 70.0, 98.0, 0.8, 1.0, 10.3, 0.08, 0.10, 0.05),

-- Morning exercise
(NOW() - INTERVAL '17 hours', '001A', 95.0, 96.0, 1.5, 2.0, 11.5, 0.3, 0.4, 0.2),
(NOW() - INTERVAL '16 hours', '001A', 125.0, 94.0, 3.0, 4.0, 13.5, 0.8, 1.0, 0.5),
(NOW() - INTERVAL '15 hours', '001A', 140.0, 93.0, 4.5, 5.5, 15.0, 1.2, 1.5, 0.8),
(NOW() - INTERVAL '14 hours', '001A', 115.0, 95.0, 2.0, 2.5, 12.0, 0.5, 0.6, 0.3),

-- Post-exercise recovery
(NOW() - INTERVAL '13 hours', '001A', 85.0, 97.0, 0.5, 0.6, 10.2, 0.1, 0.12, 0.06),
(NOW() - INTERVAL '12 hours', '001A', 75.0, 98.0, 0.3, 0.4, 9.9, 0.05, 0.06, 0.03),

-- Work hours (sitting, light stress)
(NOW() - INTERVAL '11 hours', '001A', 72.0, 98.0, 0.1, 0.15, 9.82, 0.02, 0.025, 0.01),
(NOW() - INTERVAL '10 hours', '001A', 78.0, 97.5, 0.15, 0.2, 9.85, 0.025, 0.03, 0.015),
(NOW() - INTERVAL '9 hours', '001A', 82.0, 97.0, 0.2, 0.25, 9.9, 0.03, 0.04, 0.02),
(NOW() - INTERVAL '8 hours', '001A', 88.0, 96.5, 0.3, 0.4, 10.0, 0.05, 0.06, 0.03),

-- Lunch break (walking)
(NOW() - INTERVAL '7 hours', '001A', 92.0, 96.0, 1.0, 1.2, 10.8, 0.2, 0.25, 0.12),
(NOW() - INTERVAL '6 hours', '001A', 75.0, 98.0, 0.2, 0.3, 9.85, 0.03, 0.04, 0.02),

-- Afternoon work
(NOW() - INTERVAL '5 hours', '001A', 74.0, 98.0, 0.12, 0.18, 9.83, 0.022, 0.028, 0.012),
(NOW() - INTERVAL '4 hours', '001A', 76.0, 97.5, 0.15, 0.22, 9.86, 0.025, 0.032, 0.015),

-- Evening commute
(NOW() - INTERVAL '3 hours', '001A', 80.0, 97.0, 0.8, 1.0, 10.5, 0.15, 0.2, 0.1),
(NOW() - INTERVAL '2 hours', '001A', 78.0, 97.5, 0.6, 0.8, 10.2, 0.1, 0.15, 0.08),

-- Evening relaxation
(NOW() - INTERVAL '1 hour', '001A', 68.0, 98.5, 0.1, 0.15, 9.82, 0.015, 0.02, 0.008),
(NOW() - INTERVAL '30 minutes', '001A', 65.0, 99.0, 0.08, 0.1, 9.81, 0.01, 0.015, 0.006),
(NOW() - INTERVAL '10 minutes', '001A', 63.0, 99.0, 0.05, 0.08, 9.80, 0.008, 0.01, 0.004),
(NOW(), '001A', 62.0, 99.0, 0.04, 0.06, 9.81, 0.006, 0.008, 0.003);
```

---

## One-Liner Commands

### Insert 10 Normal Readings
```bash
docker exec -it timescaledb psql -U rushy -d readings -c "INSERT INTO smartwatch_readings (device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z) VALUES ('001A', 70, 98, 0.1, 0.2, 9.8, 0.01, 0.02, 0.01), ('001A', 72, 98, 0.1, 0.2, 9.8, 0.01, 0.02, 0.01), ('001A', 68, 99, 0.1, 0.2, 9.8, 0.01, 0.02, 0.01), ('001A', 71, 98, 0.1, 0.2, 9.8, 0.01, 0.02, 0.01), ('001A', 69, 98, 0.1, 0.2, 9.8, 0.01, 0.02, 0.01), ('001A', 73, 97, 0.1, 0.2, 9.8, 0.01, 0.02, 0.01), ('001A', 67, 99, 0.1, 0.2, 9.8, 0.01, 0.02, 0.01), ('001A', 74, 98, 0.1, 0.2, 9.8, 0.01, 0.02, 0.01), ('001A', 66, 98, 0.1, 0.2, 9.8, 0.01, 0.02, 0.01), ('001A', 75, 97, 0.1, 0.2, 9.8, 0.01, 0.02, 0.01);"
```

### Insert Critical Alert Test (Tachycardia)
```bash
docker exec -it timescaledb psql -U rushy -d readings -c "INSERT INTO smartwatch_readings (device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z) VALUES ('001A', 155, 96, 0.1, 0.2, 9.8, 0.01, 0.02, 0.01);"
```

### Insert Critical Alert Test (Hypoxia)
```bash
docker exec -it timescaledb psql -U rushy -d readings -c "INSERT INTO smartwatch_readings (device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z) VALUES ('001A', 88, 84, 0.1, 0.2, 9.8, 0.01, 0.02, 0.01);"
```

### Insert Exercise Data
```bash
docker exec -it timescaledb psql -U rushy -d readings -c "INSERT INTO smartwatch_readings (device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z) VALUES ('001A', 130, 94, 3.5, 4.5, 14.0, 1.0, 1.4, 0.7);"
```

---

## Verification Queries

### Check Latest Data
```sql
SELECT time, device_id, heart_rate, spo2, prediction, is_anomaly, cluster_label 
FROM smartwatch_readings 
ORDER BY time DESC LIMIT 10;
```

### Check Cluster Distribution
```sql
SELECT cluster_label, COUNT(*) as count 
FROM smartwatch_readings 
WHERE cluster_label IS NOT NULL 
GROUP BY cluster_label;
```

### Check Predictions
```sql
SELECT prediction, COUNT(*) as count 
FROM smartwatch_readings 
WHERE prediction IS NOT NULL 
GROUP BY prediction;
```

### Check Anomalies
```sql
SELECT time, heart_rate, spo2, prediction, is_anomaly 
FROM smartwatch_readings 
WHERE is_anomaly = TRUE 
ORDER BY time DESC LIMIT 10;
```

### Check Notifications Generated
```sql
SELECT * FROM notifications ORDER BY sent_at DESC LIMIT 10;
```

---

## Data Ranges Reference

| Condition | Heart Rate | SpO2 | Accel Mag | Gyro Mag | Key Differentiator |
|-----------|------------|------|-----------|----------|-------------------|
| Resting | 55-70 | 98-100 | 9.8-10.0 | < 0.05 | Very low movement |
| Normal | 60-80 | 96-99 | 9.8-10.5 | 0.02-0.1 | Baseline |
| Light Activity | 80-100 | 95-98 | 10.5-12.0 | 0.3-0.8 | Walking, light movement |
| **Exercise** | 100-160 | 92-96 | **14.0-20.0** | **1.5-3.5** | **HIGH motion + HIGH HR** |
| **Tachycardia** | > 100 | Normal | **9.8-10.5** | **< 0.1** | **LOW motion + HIGH HR** |
| Bradycardia | < 60 | Normal | 9.8-10.5 | < 0.1 | Low HR at rest |
| Hypoxia | Any | < 92 | Any | Any | Low oxygen |
| Stressed | 90-110 | 94-97 | 10.0-11.0 | 0.1-0.3 | Elevated HR, slight tension |

### Key: Exercise vs Tachycardia
- **Exercise**: HR 130 + accel_mag 17 + gyro_mag 2.5 → Running/jogging
- **Tachycardia**: HR 130 + accel_mag 9.8 + gyro_mag 0.02 → Abnormal (sitting with high HR)

### Accel Magnitude Formula
```
accel_mag = sqrt(accel_x² + accel_y² + accel_z²)
```
- At rest: ~9.8 m/s² (gravity only)
- Walking: ~10.5-12 m/s²
- Running: ~15-20 m/s²
- Jumping: ~25+ m/s²

---

## Clear Test Data

⚠️ **Use with caution!**

```sql
-- Delete all readings (keeps table structure)
TRUNCATE smartwatch_readings;

-- Delete only test device data
DELETE FROM smartwatch_readings WHERE device_id = '001A';

-- Delete data older than 7 days
DELETE FROM smartwatch_readings WHERE time < NOW() - INTERVAL '7 days';
```
