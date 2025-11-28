# Database Schema Reference

## Connection Details

```bash
ssh -i "newkey.pem" rushy@34.197.138.31
docker exec -it timescaledb psql -U rushy -d readings
```

---

## Tables Overview

| Table | Purpose |
|-------|---------|
| `smartwatch_readings` | Sensor data & ML predictions (TimescaleDB hypertable) |
| `users` | User accounts |
| `devices` | Registered devices linked to users |
| `notifications` | Push notifications & alerts |
| `emergency_contacts` | User emergency contacts |
| `user_settings` | User preferences & thresholds |
| `health_summaries` | Daily health trend summaries |

---

## Table Definitions

### `users`

User accounts for authentication.

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | SERIAL | PRIMARY KEY |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL |
| `password_hash` | VARCHAR(255) | NOT NULL |
| `full_name` | VARCHAR(255) | |
| `phone` | VARCHAR(50) | |
| `is_active` | BOOLEAN | DEFAULT TRUE |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() |

### `devices`

Devices registered to users (ESP32, mobile, etc).

| Column | Type | Constraints |
|--------|------|-------------|
| `device_id` | VARCHAR(100) | PRIMARY KEY |
| `user_id` | INTEGER | REFERENCES users(id) |
| `fcm_token` | VARCHAR(255) | Firebase Cloud Messaging token |
| `expo_push_token` | VARCHAR(255) | Expo push notification token |
| `platform` | VARCHAR(50) | DEFAULT 'android' |
| `device_name` | VARCHAR(255) | |
| `is_active` | BOOLEAN | DEFAULT TRUE |
| `last_seen` | TIMESTAMPTZ | |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() |

### `smartwatch_readings` (TimescaleDB Hypertable)

Main table for storing smartwatch sensor data and ML predictions.

| Column | Type | Constraints |
|--------|------|-------------|
| `time` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |
| `device_id` | VARCHAR(100) | Links to devices table |
| `heart_rate` | REAL | NOT NULL |
| `spo2` | REAL | NOT NULL |
| `accel_x` | REAL | |
| `accel_y` | REAL | |
| `accel_z` | REAL | |
| `gyro_x` | REAL | |
| `gyro_y` | REAL | |
| `gyro_z` | REAL | |
| `hr_diff` | REAL | |
| `spo2_diff` | REAL | |
| `stress_index` | REAL | |
| `hr_spo2_ratio` | REAL | |
| `accel_mag` | REAL | |
| `gyro_mag` | REAL | |
| `prediction` | VARCHAR(50) | |
| `is_anomaly` | BOOLEAN | |
| `forecasted_prediction` | VARCHAR(50) | |
| `cluster_id` | INTEGER | |
| `cluster_label` | VARCHAR(50) | |

### `notifications`

Push notifications and alerts sent to users.

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | SERIAL | PRIMARY KEY |
| `device_id` | VARCHAR(100) | |
| `user_id` | INTEGER | REFERENCES users(id) |
| `notification_type` | VARCHAR(50) | 'anomaly', 'critical', 'predictive', 'info' |
| `title` | VARCHAR(255) | |
| `body` | TEXT | |
| `data` | JSONB | Additional data payload |
| `sent_at` | TIMESTAMPTZ | DEFAULT NOW() |
| `read_at` | TIMESTAMPTZ | NULL until read |

### `emergency_contacts`

Emergency contacts for each user.

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | SERIAL | PRIMARY KEY |
| `user_id` | INTEGER | REFERENCES users(id), NOT NULL |
| `name` | VARCHAR(255) | NOT NULL |
| `phone` | VARCHAR(50) | NOT NULL |
| `relationship` | VARCHAR(100) | |
| `is_primary` | BOOLEAN | DEFAULT FALSE |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() |

### `user_settings`

User preferences for alerts and thresholds.

| Column | Type | Constraints |
|--------|------|-------------|
| `user_id` | INTEGER | PRIMARY KEY, REFERENCES users(id) |
| `low_spo2_threshold` | REAL | DEFAULT 92.0 |
| `high_hr_threshold` | REAL | DEFAULT 120.0 |
| `low_hr_threshold` | REAL | DEFAULT 50.0 |
| `enable_predictive_alerts` | BOOLEAN | DEFAULT TRUE |
| `enable_anomaly_alerts` | BOOLEAN | DEFAULT TRUE |
| `enable_emergency_alerts` | BOOLEAN | DEFAULT TRUE |
| `enable_sound` | BOOLEAN | DEFAULT TRUE |
| `enable_vibration` | BOOLEAN | DEFAULT TRUE |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() |

### `health_summaries`

Long-term health summary statistics (weekly trends).

| Column | Type | Constraints |
|--------|------|-------------|
| `summary_date` | DATE | PRIMARY KEY |
| `avg_resting_hr` | REAL | |
| `minutes_in_stress` | INTEGER | |
| `minutes_exercising` | INTEGER | |
| `total_anomalies` | INTEGER | |
| `resting_hr_weekly_change` | REAL | |

---

## Views

### `v_smartwatch_data_ordered`

Reporting view for smartwatch data.

```sql
CREATE OR REPLACE VIEW v_smartwatch_data_ordered AS
SELECT
    time, device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z,
    hr_diff, spo2_diff, stress_index, hr_spo2_ratio, accel_mag, gyro_mag,
    prediction, is_anomaly, forecasted_prediction, cluster_id, cluster_label
FROM smartwatch_readings;
```

---

## Indexes

```sql
-- Speed up finding unprocessed rows
CREATE INDEX idx_unprocessed ON smartwatch_readings (time DESC) 
WHERE prediction IS NULL OR is_anomaly IS NULL;

-- Speed up device lookups
CREATE INDEX idx_readings_device ON smartwatch_readings (device_id, time DESC);

-- Speed up user notifications lookup
CREATE INDEX idx_notifications_user ON notifications (user_id, sent_at DESC);

-- Speed up device user lookup
CREATE INDEX idx_devices_user ON devices (user_id);
```

---

## Setup Commands (Run in Database)

Copy and run this in the database to create all missing tables:

```sql
-- ========================
-- USER MANAGEMENT TABLES
-- ========================

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    phone VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Devices table
CREATE TABLE IF NOT EXISTS devices (
    device_id VARCHAR(100) PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    fcm_token VARCHAR(255),
    expo_push_token VARCHAR(255),
    platform VARCHAR(50) DEFAULT 'android',
    device_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    last_seen TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(100),
    user_id INTEGER REFERENCES users(id),
    notification_type VARCHAR(50),
    title VARCHAR(255),
    body TEXT,
    data JSONB,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    read_at TIMESTAMPTZ
);

-- Emergency contacts table
CREATE TABLE IF NOT EXISTS emergency_contacts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) NOT NULL,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(50) NOT NULL,
    relationship VARCHAR(100),
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User settings table
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    low_spo2_threshold REAL DEFAULT 92.0,
    high_hr_threshold REAL DEFAULT 120.0,
    low_hr_threshold REAL DEFAULT 50.0,
    enable_predictive_alerts BOOLEAN DEFAULT TRUE,
    enable_anomaly_alerts BOOLEAN DEFAULT TRUE,
    enable_emergency_alerts BOOLEAN DEFAULT TRUE,
    enable_sound BOOLEAN DEFAULT TRUE,
    enable_vibration BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ========================
-- HEALTH DATA TABLES
-- ========================

-- Add device_id to smartwatch_readings if not exists
ALTER TABLE smartwatch_readings ADD COLUMN IF NOT EXISTS device_id VARCHAR(100);

-- Health summaries (if not exists)
CREATE TABLE IF NOT EXISTS health_summaries (
    summary_date DATE PRIMARY KEY,
    avg_resting_hr REAL,
    minutes_in_stress INTEGER,
    minutes_exercising INTEGER,
    total_anomalies INTEGER,
    resting_hr_weekly_change REAL
);

-- ========================
-- INDEXES
-- ========================

CREATE INDEX IF NOT EXISTS idx_readings_device ON smartwatch_readings (device_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications (user_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_devices_user ON devices (user_id);

-- ========================
-- VIEWS
-- ========================

CREATE OR REPLACE VIEW v_smartwatch_data_ordered AS
SELECT
    time, device_id, heart_rate, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z,
    hr_diff, spo2_diff, stress_index, hr_spo2_ratio, accel_mag, gyro_mag,
    prediction, is_anomaly, forecasted_prediction, cluster_id, cluster_label
FROM smartwatch_readings;
```

---

## Common Queries

```sql
-- Check all tables exist
\dt

-- View latest 10 records
SELECT * FROM v_smartwatch_data_ordered ORDER BY time DESC LIMIT 10;

-- View user and their devices
SELECT u.id, u.email, d.device_id, d.last_seen 
FROM users u 
LEFT JOIN devices d ON u.id = d.user_id;

-- View readings for a specific user
SELECT sr.* FROM smartwatch_readings sr
JOIN devices d ON sr.device_id = d.device_id
WHERE d.user_id = 1
ORDER BY sr.time DESC LIMIT 10;

-- Check notifications for a user
SELECT * FROM notifications WHERE user_id = 1 ORDER BY sent_at DESC;

-- View emergency contacts for a user
SELECT * FROM emergency_contacts WHERE user_id = 1;

-- View user settings
SELECT * FROM user_settings WHERE user_id = 1;
```

---

## Data Flow Diagram

```
ESP32 Device (device_id: "001A")
       │
       ▼ POST /api/v1/ingest
┌──────────────────────────────┐
│   smartwatch_readings        │
│   (device_id = "001A")       │
└──────────────────────────────┘
       │
       ▼ JOIN via device_id
┌──────────────────────────────┐
│   devices                    │
│   (device_id → user_id)      │
└──────────────────────────────┘
       │
       ▼ 
┌──────────────────────────────┐
│   users                      │
│   (user account)             │
└──────────────────────────────┘
       │
       ▼ Alerts trigger notifications
┌──────────────────────────────┐
│   notifications              │
│   (sent to mobile app)       │
└──────────────────────────────┘
```

---

## Quick Setup (One Command)

SSH into the server and run the full setup:

```bash
ssh -i "newkey.pem" rushy@34.197.138.31
docker exec -it timescaledb psql -U rushy -d readings -c "
CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, email VARCHAR(255) UNIQUE NOT NULL, password_hash VARCHAR(255) NOT NULL, full_name VARCHAR(255), phone VARCHAR(50), is_active BOOLEAN DEFAULT TRUE, created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS devices (device_id VARCHAR(100) PRIMARY KEY, user_id INTEGER REFERENCES users(id), fcm_token VARCHAR(255), expo_push_token VARCHAR(255), platform VARCHAR(50) DEFAULT 'android', device_name VARCHAR(255), is_active BOOLEAN DEFAULT TRUE, last_seen TIMESTAMPTZ, created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS notifications (id SERIAL PRIMARY KEY, device_id VARCHAR(100), user_id INTEGER REFERENCES users(id), notification_type VARCHAR(50), title VARCHAR(255), body TEXT, data JSONB, sent_at TIMESTAMPTZ DEFAULT NOW(), read_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS emergency_contacts (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id) NOT NULL, name VARCHAR(255) NOT NULL, phone VARCHAR(50) NOT NULL, relationship VARCHAR(100), is_primary BOOLEAN DEFAULT FALSE, created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS user_settings (user_id INTEGER PRIMARY KEY REFERENCES users(id), low_spo2_threshold REAL DEFAULT 92.0, high_hr_threshold REAL DEFAULT 120.0, low_hr_threshold REAL DEFAULT 50.0, enable_predictive_alerts BOOLEAN DEFAULT TRUE, enable_anomaly_alerts BOOLEAN DEFAULT TRUE, enable_emergency_alerts BOOLEAN DEFAULT TRUE, enable_sound BOOLEAN DEFAULT TRUE, enable_vibration BOOLEAN DEFAULT TRUE, updated_at TIMESTAMPTZ DEFAULT NOW());
ALTER TABLE smartwatch_readings ADD COLUMN IF NOT EXISTS device_id VARCHAR(100);
CREATE TABLE IF NOT EXISTS health_summaries (summary_date DATE PRIMARY KEY, avg_resting_hr REAL, minutes_in_stress INTEGER, minutes_exercising INTEGER, total_anomalies INTEGER, resting_hr_weekly_change REAL);
"
```
