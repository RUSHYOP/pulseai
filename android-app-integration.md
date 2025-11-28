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

#### Get DBSCAN Cluster Data (for Visualization)
```http
GET /api/v1/health/clusters?hours=24
Authorization: Bearer <token>
```

**Response:**
```json
{
  "clusters": [
    {
      "label": "Resting",
      "cluster_id": 0,
      "color": "#4CAF50",
      "points": [
        {"x": 68, "y": 98, "stress_index": 0.12, "accel_mag": 9.8, "prediction": "Normal", "time": "2025-11-28T10:00:00Z"},
        {"x": 72, "y": 97, "stress_index": 0.15, "accel_mag": 9.9, "prediction": "Normal", "time": "2025-11-28T10:05:00Z"}
      ]
    },
    {
      "label": "Light Activity",
      "cluster_id": 1,
      "color": "#2196F3",
      "points": [
        {"x": 85, "y": 96, "stress_index": 0.25, "accel_mag": 12.5, "prediction": "Exercising", "time": "2025-11-28T11:00:00Z"}
      ]
    },
    {
      "label": "Moderate Activity",
      "cluster_id": 2,
      "color": "#FF9800",
      "points": []
    }
  ],
  "total_points": 150,
  "axis_labels": {
    "x": "Heart Rate (bpm)",
    "y": "SpO2 (%)"
  }
}
```

**Cluster Colors:**
| Cluster ID | Label | Color |
|------------|-------|-------|
| -1 | Noise/Undefined | #808080 (Gray) |
| 0 | Resting | #4CAF50 (Green) |
| 1 | Light Activity | #2196F3 (Blue) |
| 2 | Moderate Activity | #FF9800 (Orange) |
| 3 | Commuting | #9C27B0 (Purple) |

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
| **Cluster Data** | `GET /api/v1/health/clusters` | Yes |
| Get Alerts | `GET /api/v1/alerts` | Yes |
| Mark Alert Read | `PATCH /api/v1/alerts/{id}/read` | Yes |
| Emergency Contacts | `GET/POST/PUT/DELETE /api/v1/emergency-contacts` | Yes |
| Settings | `GET/PUT /api/v1/settings` | Yes |
| WebSocket | `ws://34.197.138.31:8000/ws/{device_id}` | No |

---

## 📈 DBSCAN Cluster Visualization Component

### Install Dependencies
```bash
npm install react-native-svg
# or for Expo:
expo install react-native-svg
```

### ClusterChart.tsx
```typescript
import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, Dimensions, ActivityIndicator } from 'react-native';
import { Svg, Circle, G, Line, Text as SvgText } from 'react-native-svg';
import { api } from '../services/api';

interface ClusterPoint {
  x: number;
  y: number;
  stress_index: number;
  accel_mag: number;
  prediction: string;
  time: string;
}

interface Cluster {
  label: string;
  cluster_id: number;
  color: string;
  points: ClusterPoint[];
}

interface ClusterData {
  clusters: Cluster[];
  total_points: number;
  axis_labels: { x: string; y: string };
}

const { width } = Dimensions.get('window');
const CHART_WIDTH = width - 40;
const CHART_HEIGHT = 300;
const PADDING = 50;

export const ClusterChart: React.FC<{ hours?: number }> = ({ hours = 24 }) => {
  const [data, setData] = useState<ClusterData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchClusterData();
  }, [hours]);

  const fetchClusterData = async () => {
    try {
      setLoading(true);
      const response = await api.get(`/api/v1/health/clusters?hours=${hours}`);
      setData(response.data);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch cluster data');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#6366F1" />
        <Text style={styles.loadingText}>Loading clusters...</Text>
      </View>
    );
  }

  if (error) {
    return <Text style={styles.error}>{error}</Text>;
  }

  if (!data || data.clusters.length === 0 || data.total_points === 0) {
    return (
      <View style={styles.container}>
        <Text style={styles.title}>Activity Clusters</Text>
        <Text style={styles.noData}>No cluster data available yet</Text>
      </View>
    );
  }

  // Calculate scale from all points
  const allPoints = data.clusters.flatMap(c => c.points);
  const hrValues = allPoints.map(p => p.x);
  const spo2Values = allPoints.map(p => p.y);
  
  const minX = Math.min(...hrValues) - 5;
  const maxX = Math.max(...hrValues) + 5;
  const minY = Math.min(...spo2Values) - 2;
  const maxY = Math.max(...spo2Values) + 2;

  const scaleX = (val: number) =>
    PADDING + ((val - minX) / (maxX - minX)) * (CHART_WIDTH - PADDING * 2);
  const scaleY = (val: number) =>
    CHART_HEIGHT - PADDING - ((val - minY) / (maxY - minY)) * (CHART_HEIGHT - PADDING * 2);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Activity Clusters (DBSCAN)</Text>
      <Text style={styles.subtitle}>Heart Rate vs SpO2 - Last {hours}h</Text>

      <Svg width={CHART_WIDTH} height={CHART_HEIGHT}>
        {/* Background grid */}
        <G>
          {[0, 1, 2, 3, 4].map(i => {
            const y = PADDING + (i * (CHART_HEIGHT - PADDING * 2)) / 4;
            const x = PADDING + (i * (CHART_WIDTH - PADDING * 2)) / 4;
            return (
              <G key={`grid-${i}`}>
                <Line x1={PADDING} y1={y} x2={CHART_WIDTH - PADDING} y2={y} stroke="#E5E7EB" strokeWidth={1} />
                <Line x1={x} y1={PADDING} x2={x} y2={CHART_HEIGHT - PADDING} stroke="#E5E7EB" strokeWidth={1} />
              </G>
            );
          })}
        </G>

        {/* Axis labels */}
        <SvgText x={CHART_WIDTH / 2} y={CHART_HEIGHT - 10} fontSize={11} textAnchor="middle" fill="#6B7280">
          {data.axis_labels.x}
        </SvgText>
        <SvgText x={12} y={CHART_HEIGHT / 2} fontSize={11} textAnchor="middle" fill="#6B7280" rotation="-90" origin={`12, ${CHART_HEIGHT / 2}`}>
          {data.axis_labels.y}
        </SvgText>

        {/* Axis value labels */}
        <SvgText x={PADDING} y={CHART_HEIGHT - 30} fontSize={9} fill="#9CA3AF">{minX.toFixed(0)}</SvgText>
        <SvgText x={CHART_WIDTH - PADDING} y={CHART_HEIGHT - 30} fontSize={9} textAnchor="end" fill="#9CA3AF">{maxX.toFixed(0)}</SvgText>
        <SvgText x={PADDING - 5} y={CHART_HEIGHT - PADDING} fontSize={9} textAnchor="end" fill="#9CA3AF">{minY.toFixed(0)}</SvgText>
        <SvgText x={PADDING - 5} y={PADDING + 5} fontSize={9} textAnchor="end" fill="#9CA3AF">{maxY.toFixed(0)}</SvgText>

        {/* Plot cluster points */}
        {data.clusters.map((cluster) =>
          cluster.points.map((point, idx) => (
            <Circle
              key={`${cluster.label}-${idx}`}
              cx={scaleX(point.x)}
              cy={scaleY(point.y)}
              r={5}
              fill={cluster.color}
              opacity={0.75}
            />
          ))
        )}
      </Svg>

      {/* Legend */}
      <View style={styles.legend}>
        {data.clusters
          .filter(c => c.points.length > 0)
          .map((cluster) => (
            <View key={cluster.label} style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: cluster.color }]} />
              <Text style={styles.legendText}>
                {cluster.label} ({cluster.points.length})
              </Text>
            </View>
          ))}
      </View>

      <Text style={styles.totalPoints}>
        {data.total_points} data points analyzed
      </Text>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 16,
    margin: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 4,
  },
  centered: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: 40,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1F2937',
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 13,
    color: '#6B7280',
    marginBottom: 16,
  },
  loadingText: {
    marginTop: 12,
    color: '#6B7280',
  },
  error: {
    color: '#EF4444',
    textAlign: 'center',
    padding: 20,
  },
  noData: {
    color: '#9CA3AF',
    textAlign: 'center',
    paddingVertical: 40,
  },
  legend: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: 16,
    gap: 16,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  legendDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    marginRight: 6,
  },
  legendText: {
    fontSize: 12,
    color: '#4B5563',
  },
  totalPoints: {
    marginTop: 12,
    fontSize: 11,
    color: '#9CA3AF',
    textAlign: 'center',
  },
});

export default ClusterChart;
```

### Usage in Your App
```typescript
import { ClusterChart } from './components/ClusterChart';

// In your dashboard or analytics screen:
<ClusterChart hours={24} />

// Or for weekly view:
<ClusterChart hours={168} />
```
