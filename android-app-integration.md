# PulsAI Android App - Cloud Integration Guide

**Last Updated:** November 28, 2025  
**Server:** `http://34.197.138.31:8000`  
**WebSocket:** `ws://34.197.138.31:8000/ws/{device_id}`

---

## 🔄 What Changed on the Server

### New Database Tables Added
- `users` - User accounts with email/password authentication
- `devices` - Device registration for push notifications (linked to users)
- `notifications` - Alert history and push notification records
- `emergency_contacts` - User's emergency contacts
- `user_settings` - User preferences and alert thresholds
- `device_id` column added to `smartwatch_readings` table

### New Backend Features
- **JWT Authentication** - 30-day access tokens
- **User Accounts** - Full registration/login system
- **Device Registration** - Link devices to user accounts
- **Push Notification System** - Automatic alerts on anomalies/critical conditions
- **WebSocket Support** - Real-time data streaming to app
- **User-specific Data** - Health data filtered by authenticated user

---

## 📡 API Endpoints

### Base URL
```
http://34.197.138.31:8000
```

### Authentication Header (for protected endpoints)
```
Authorization: Bearer <access_token>
```

---

### 🔐 Authentication Endpoints

#### Register New User
```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123",
  "full_name": "John Doe",
  "phone": "+1234567890"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "full_name": "John Doe"
  }
}
```

#### Login
```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```

**Response:** Same as register

#### Get Current User Info
```http
GET /api/v1/auth/me
Authorization: Bearer <token>
```

---

### 📱 Device Endpoints

#### Register Device (for push notifications)
```http
POST /api/v1/devices/register
Authorization: Bearer <token>
Content-Type: application/json

{
  "device_id": "android-pixel-1234567890",
  "fcm_token": "firebase_cloud_messaging_token",
  "expo_push_token": "ExponentPushToken[xxx]",
  "platform": "android",
  "device_name": "Pixel 7 Pro"
}
```

#### Get User's Devices
```http
GET /api/v1/devices
Authorization: Bearer <token>
```

---

### ❤️ Health Data Endpoints

#### Ingest Sensor Data (from smartwatch)
```http
POST /api/v1/ingest
Authorization: Bearer <token> (optional)
Content-Type: application/json

{
  "device_id": "android-pixel-1234567890",
  "heart_rate": 72.0,
  "spo2": 98.0,
  "accel_x": 0.1,
  "accel_y": 0.2,
  "accel_z": 9.8,
  "gyro_x": 0.01,
  "gyro_y": 0.02,
  "gyro_z": 0.01
}
```

#### Get Latest Health Reading
```http
GET /api/v1/health/latest
Authorization: Bearer <token>
```

**Response:**
```json
{
  "time": "2025-11-28T10:30:00Z",
  "device_id": "android-pixel-1234567890",
  "heart_rate": 72.0,
  "spo2": 98.0,
  "prediction": "Normal",
  "is_anomaly": false,
  "forecasted_prediction": "Normal",
  "stress_index": 0.15,
  "cluster_label": "Resting",
  "accel_mag": 9.82
}
```

#### Get Health History
```http
GET /api/v1/health/history?hours=24&limit=500
Authorization: Bearer <token>
```

#### Get Health Summary (24h)
```http
GET /api/v1/health/summary
Authorization: Bearer <token>
```

**Response:**
```json
{
  "state_distribution_percent": {
    "Normal": 75.5,
    "Exercising": 15.2,
    "Resting": 9.3
  },
  "anomaly_count": 2,
  "average_resting_hr": 68.5,
  "activity_distribution_percent": {
    "Resting": 60.0,
    "Light Activity": 25.0,
    "Moderate Activity": 15.0
  }
}
```

---

### 🔔 Alerts/Notifications Endpoints

#### Get All Alerts
```http
GET /api/v1/alerts?limit=50&unread_only=false
Authorization: Bearer <token>
```

**Response:**
```json
[
  {
    "id": 1,
    "type": "anomaly",
    "title": "⚠️ Health Anomaly Detected",
    "body": "Unusual reading detected. HR: 145, SpO2: 89%",
    "data": {"heart_rate": 145, "spo2": 89},
    "sent_at": "2025-11-28T10:30:00Z",
    "read_at": null,
    "is_read": false
  }
]
```

#### Mark Alert as Read
```http
PATCH /api/v1/alerts/{alert_id}/read
Authorization: Bearer <token>
```

#### Mark All Alerts as Read
```http
PATCH /api/v1/alerts/read-all
Authorization: Bearer <token>
```

---

### 🆘 Emergency Contacts Endpoints

#### Get Emergency Contacts
```http
GET /api/v1/emergency-contacts
Authorization: Bearer <token>
```

**Response:**
```json
[
  {
    "id": 1,
    "name": "Mom",
    "phone": "+1234567890",
    "relationship": "Mother",
    "is_primary": true
  }
]
```

#### Add Emergency Contact
```http
POST /api/v1/emergency-contacts
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Mom",
  "phone": "+1234567890",
  "relationship": "Mother",
  "is_primary": true
}
```

#### Update Emergency Contact
```http
PUT /api/v1/emergency-contacts/{contact_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Mom",
  "phone": "+1234567890",
  "relationship": "Mother",
  "is_primary": true
}
```

#### Delete Emergency Contact
```http
DELETE /api/v1/emergency-contacts/{contact_id}
Authorization: Bearer <token>
```

---

### ⚙️ User Settings Endpoints

#### Get Settings
```http
GET /api/v1/settings
Authorization: Bearer <token>
```

**Response:**
```json
{
  "low_spo2_threshold": 92.0,
  "high_hr_threshold": 120.0,
  "low_hr_threshold": 50.0,
  "enable_predictive_alerts": true,
  "enable_anomaly_alerts": true,
  "enable_emergency_alerts": true,
  "enable_sound": true,
  "enable_vibration": true
}
```

#### Update Settings
```http
PUT /api/v1/settings
Authorization: Bearer <token>
Content-Type: application/json

{
  "low_spo2_threshold": 90.0,
  "high_hr_threshold": 130.0,
  "low_hr_threshold": 45.0,
  "enable_predictive_alerts": true,
  "enable_anomaly_alerts": true,
  "enable_emergency_alerts": true,
  "enable_sound": true,
  "enable_vibration": true
}
```

---

### 🔌 WebSocket (Real-time Data)

#### Connect
```
ws://34.197.138.31:8000/ws/{device_id}
```

#### Keep-alive (send every 30 seconds)
```json
"ping"
```

#### Server Response
```json
{"type": "pong", "timestamp": "2025-11-28T10:30:00Z"}
```

#### Real-time Notification (server pushes)
```json
{
  "type": "notification",
  "notification_type": "anomaly",
  "title": "⚠️ Health Anomaly Detected",
  "body": "Unusual reading detected. HR: 145, SpO2: 89%",
  "data": {"heart_rate": 145, "spo2": 89}
}
```

---

## 📱 App Implementation Checklist

### Required Changes

- [ ] **API Service** - Create axios/fetch client with base URL `http://34.197.138.31:8000`
- [ ] **Auth Flow** - Implement login/register screens that call `/api/v1/auth/*`
- [ ] **Token Storage** - Store JWT token in AsyncStorage after login
- [ ] **Auth Interceptor** - Add `Authorization: Bearer <token>` header to all requests
- [ ] **Device Registration** - Generate unique device_id and register on login
- [ ] **Dashboard** - Fetch from `/api/v1/health/latest` instead of mock data
- [ ] **Trends** - Fetch from `/api/v1/health/history` and `/api/v1/health/summary`
- [ ] **Alerts** - Fetch from `/api/v1/alerts`
- [ ] **Emergency Contacts** - CRUD via `/api/v1/emergency-contacts`
- [ ] **Settings** - Sync with `/api/v1/settings`
- [ ] **WebSocket** - Connect for real-time updates
- [ ] **Push Notifications** - Integrate Expo Push or Firebase FCM

### Config File to Create
```typescript
// src/config/api.config.ts
export const API_CONFIG = {
  BASE_URL: 'http://34.197.138.31:8000',
  WS_URL: 'ws://34.197.138.31:8000/ws',
  ENDPOINTS: {
    // Auth
    REGISTER: '/api/v1/auth/register',
    LOGIN: '/api/v1/auth/login',
    ME: '/api/v1/auth/me',
    // Device
    REGISTER_DEVICE: '/api/v1/devices/register',
    DEVICES: '/api/v1/devices',
    // Health
    INGEST: '/api/v1/ingest',
    LATEST: '/api/v1/health/latest',
    HISTORY: '/api/v1/health/history',
    SUMMARY: '/api/v1/health/summary',
    // Alerts
    ALERTS: '/api/v1/alerts',
    // Emergency
    EMERGENCY_CONTACTS: '/api/v1/emergency-contacts',
    // Settings
    SETTINGS: '/api/v1/settings',
  }
};
```

---

## 🔔 Automatic Notifications

The server automatically creates notifications when:

| Condition | Notification Type | Example |
|-----------|------------------|---------|
| `is_anomaly = true` | `anomaly` | "⚠️ Health Anomaly Detected" |
| `prediction` = Tachycardia, Bradycardia, Arrhythmia, Hypoxia | `critical` | "🚨 Critical Health Alert" |

These are stored in the `notifications` table and:
1. Available via `GET /api/v1/alerts`
2. Pushed via WebSocket if connected
3. (Future) Sent via Firebase FCM if `fcm_token` is registered

---

## 🧪 Test Credentials

```
Email: test@pulsai.health
Password: password123
```

Register first, then login to get your access token.

---

## 📊 Health State Predictions

The ML model classifies readings into these states:
- `Normal` - Healthy baseline
- `Resting` - Low activity, relaxed
- `Exercising` - Physical activity detected
- `Stressed` - Elevated stress indicators
- `Tachycardia` - High heart rate (>100 bpm)
- `Bradycardia` - Low heart rate (<60 bpm)
- `Hypoxia` - Low blood oxygen (<92%)
- `Arrhythmia` - Irregular heart rhythm

---

## 🔗 Quick Reference

| Feature | Endpoint | Auth Required |
|---------|----------|---------------|
| Register | `POST /api/v1/auth/register` | No |
| Login | `POST /api/v1/auth/login` | No |
| User Info | `GET /api/v1/auth/me` | Yes |
| Register Device | `POST /api/v1/devices/register` | Yes |
| Ingest Data | `POST /api/v1/ingest` | Optional |
| Latest Reading | `GET /api/v1/health/latest` | Yes |
| Health History | `GET /api/v1/health/history` | Yes |
| Health Summary | `GET /api/v1/health/summary` | Yes |
| Get Alerts | `GET /api/v1/alerts` | Yes |
| Mark Alert Read | `PATCH /api/v1/alerts/{id}/read` | Yes |
| Emergency Contacts | `GET/POST/PUT/DELETE /api/v1/emergency-contacts` | Yes |
| Settings | `GET/PUT /api/v1/settings` | Yes |
| WebSocket | `ws://34.197.138.31:8000/ws/{device_id}` | No |
