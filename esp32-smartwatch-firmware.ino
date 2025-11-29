/*
 * FULL SYSTEM: ESP32 + SIM900A + MAX30102 + MPU6050
 *
 * FUNCTIONALITIES:
 * 1. Collect HR, SpO2, and GPS (placeholder) every 2 minutes.
 * 2. Transmit data to Cloud (HTTP POST).
 * 3. Edge Detection (Mini Decision Tree) for extreme physiological values.
 * 4. Fall Detection (Simplified SVM-like logic).
 * 5. Emergency Alerting: SMS + Continuous Calls until response.
 *
 * WIRING:
 * 1. SIM900A RX  -> GPIO 5 (TX2)
 * 2. SIM900A TX  -> GPIO 4 (RX2)
 * 3. SIM900A GND -> ESP32 GND
 * 4. SIM900A VCC -> External 5V 2A
 * 5. Sensors SDA -> GPIO 21
 * 6. Sensors SCL -> GPIO 22
 * 7. Sensors VCC -> 3.3V
 * 8. Sensors GND -> GND
 */

#include <Wire.h>
#include <HardwareSerial.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "MAX30105.h"
#include "heartRate.h"
#include "spo2_algorithm.h" // SpO2 calculation
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <esp_system.h>  // For device ID
#include <esp_task_wdt.h> // Watchdog timer

// --- PINS ---
#define RXD2 4
#define TXD2 5
#define EMERGENCY_BUTTON_PIN 0  // GPIO 0 (BOOT button on most ESP32 boards)

// --- CONFIGURATION ---
const char* ssid = "Rushy's Z10";
const char* password = "12345678";
const char* serverUrl = "http://34.197.138.31:8000/api/v1/ingest"; // Your cloud endpoint
const String EMERGENCY_PHONE = "+917338033618"; // Emergency contact
const unsigned long GSM_DELAY = 6000;
const unsigned long DATA_INTERVAL = 120000; // 2 minutes
const unsigned long HTTP_TIMEOUT = 10000; // 10 second HTTP timeout
const int MAX_UPLOAD_RETRIES = 3; // Retry failed uploads
const unsigned long WIFI_RECONNECT_INTERVAL = 30000; // Try reconnect every 30s
const unsigned long WDT_TIMEOUT = 30; // Watchdog timeout in seconds

// GSM/GPRS Configuration - Update APN for your carrier
const char* gsmApn = "airtelgprs.com"; // Airtel India APN (change for your carrier)
const char* gsmUser = ""; // Usually empty
const char* gsmPass = ""; // Usually empty
const char* serverHost = "34.197.138.31";
const int serverPort = 8000;
const char* serverPath = "/ingest";

// Device ID (unique per ESP32)
String deviceId = "001A";

// --- THRESHOLDS (Decision Tree) ---
const float HR_HIGH_THRESH = 140.0;
const float HR_LOW_THRESH = 40.0;
const float SPO2_LOW_THRESH = 90.0;

// --- FALL DETECTION THRESHOLDS (SVM-like) ---
const float ACCEL_FALL_THRESH = 25.0; // High acceleration magnitude (m/s^2) indicating impact
const float GYRO_FALL_THRESH = 200.0; // High rotation rate (rad/s) indicating tumble

// --- OBJECTS ---
HardwareSerial gsmSerial(2);
MAX30105 particleSensor;
Adafruit_MPU6050 mpu;

// --- GLOBALS ---
unsigned long previousMillis = 0;
bool emergencyActive = false;
bool emergencyHandled = false; // Tracks if the emergency has been acknowledged
unsigned long lastCallTime = 0;
const unsigned long CALL_INTERVAL = 30000; // Retry call every 30 seconds if active

// Variables for MAX30102 - Improved averaging
const byte RATE_SIZE = 8; // Increased for smoother readings
byte rates[RATE_SIZE];
byte rateSpot = 0;
long lastBeat = 0;
float beatsPerMinute;
int beatAvg = 0;
int validBeatCount = 0; // Track how many valid readings we have

// SpO2 calculation buffers
#define BUFFER_LENGTH 100
uint32_t irBuffer[BUFFER_LENGTH];
uint32_t redBuffer[BUFFER_LENGTH];
int32_t spo2Value;
int8_t validSPO2;
int32_t heartRateValue;
int8_t validHeartRate;
unsigned long lastSpO2Calc = 0;
const unsigned long SPO2_CALC_INTERVAL = 5000; // Calculate SpO2 every 5 seconds
float lastValidSpO2 = 0;
float lastValidHR = 0;
bool wasFingerDetected = false; // Track finger state for reset

// Fall detection confirmation
unsigned long fallDetectedTime = 0;
bool fallPending = false;
const unsigned long FALL_CONFIRM_DELAY = 300; // 300ms confirmation delay
const float POST_FALL_STILLNESS_THRESH = 12.0; // Low movement after fall

// WiFi reconnection tracking
unsigned long lastWiFiCheck = 0;
bool wifiConnected = false;

// GSM/GPRS status tracking
bool gprsConnected = false;
unsigned long lastGprsCheck = 0;
const unsigned long GPRS_CHECK_INTERVAL = 60000; // Check GPRS every 60s

// Non-blocking SpO2 collection
byte spo2SampleIndex = 0;
bool spo2CollectionActive = false;
unsigned long lastSpo2Sample = 0;
const unsigned long SPO2_SAMPLE_INTERVAL = 10; // ~10ms between samples

// Data queue for offline storage (simple buffer)
#define DATA_QUEUE_SIZE 5
struct SensorData {
  float hr;
  float spo2;
  float accel_x, accel_y, accel_z;
  float gyro_x, gyro_y, gyro_z;
  bool pending;
};
SensorData dataQueue[DATA_QUEUE_SIZE];
byte queueHead = 0;

void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);
  Serial.println("\n--- INITIALIZING SYSTEM ---");

  // 0. Generate unique Device ID from ESP32 MAC address
  uint8_t mac[6];
  WiFi.macAddress(mac);
  char macStr[18];
  sprintf(macStr, "%02X%02X%02X%02X%02X%02X", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  deviceId = String(macStr);
  Serial.println("Device ID: " + deviceId);

  // Initialize data queue
  for (int i = 0; i < DATA_QUEUE_SIZE; i++) {
    dataQueue[i].pending = false;
  }

  // 1. GSM - Allow more time for module to initialize
  gsmSerial.begin(9600, SERIAL_8N1, RXD2, TXD2);
  Serial.print("Waiting for GSM module...");
  delay(GSM_DELAY);
  
  // Clear any garbage data
  while (gsmSerial.available()) gsmSerial.read();
  
  // Try multiple times to connect to GSM
  bool gsmReady = false;
  for (int i = 0; i < 5; i++) {
    Serial.print(".");
    if (sendATCommand("AT", "OK", 2000)) {
      gsmReady = true;
      break;
    }
    delay(1000);
  }
  
  if (gsmReady) {
    Serial.println(" GSM Ready!");
    sendATCommand("AT+CMGF=1", "OK", 2000); // Text mode
    sendATCommand("AT+CNMI=1,2,0,0,0", "OK", 2000); // SMS notifications
  } else {
    Serial.println(" GSM not responding - SMS/calls disabled");
  }

  // 2. WiFi with timeout
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  unsigned long wifiStart = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < 15000) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println(" Connected!");
    wifiConnected = true;
  } else {
    Serial.println(" Failed! Will retry later.");
    wifiConnected = false;
  }

  // 3. Initialize Watchdog Timer (30 seconds)
  // First, try to deinit in case it's already running
  esp_task_wdt_deinit();
  
  esp_task_wdt_config_t wdt_config = {
    .timeout_ms = WDT_TIMEOUT * 1000,
    .idle_core_mask = (1 << portNUM_PROCESSORS) - 1,
    .trigger_panic = true
  };
  
  esp_err_t wdt_err = esp_task_wdt_init(&wdt_config);
  if (wdt_err == ESP_OK) {
    esp_task_wdt_add(NULL);
    Serial.println("✅ Watchdog Timer Enabled (" + String(WDT_TIMEOUT) + "s)");
  } else {
    Serial.println("⚠️ Watchdog setup skipped (already configured)");
  }

  // 3. Sensors
  Wire.begin();
  if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("❌ MAX30102 Not Found");
  } else {
    // Optimized settings for SpO2 and HR
    byte ledBrightness = 60;  // 0-255
    byte sampleAverage = 4;   // 1, 2, 4, 8, 16, 32
    byte ledMode = 2;         // 1 = Red only, 2 = Red + IR (for SpO2)
    byte sampleRate = 100;    // 50, 100, 200, 400, 800, 1000, 1600, 3200
    int pulseWidth = 411;     // 69, 118, 215, 411
    int adcRange = 4096;      // 2048, 4096, 8192, 16384
    
    particleSensor.setup(ledBrightness, sampleAverage, ledMode, sampleRate, pulseWidth, adcRange);
    Serial.println("✅ MAX30102 Ready");
  }

  if (!mpu.begin()) {
    Serial.println("❌ MPU6050 Not Found");
  } else {
    mpu.setAccelerometerRange(MPU6050_RANGE_16_G); // Increased range for fall detection
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
    Serial.println("✅ MPU6050 Ready");
  }
  
  // 4. Emergency Button Setup
  pinMode(EMERGENCY_BUTTON_PIN, INPUT_PULLUP);
  Serial.println("✅ Emergency Button Ready (GPIO " + String(EMERGENCY_BUTTON_PIN) + ")");
  Serial.println("\n=== MANUAL EMERGENCY TRIGGER ===");
  Serial.println("Send 'E' or 'e' via Serial Monitor to trigger test emergency");
  Serial.println("Or press BOOT button (GPIO0) for 2 seconds");
  Serial.println("Send 'R' or 'r' to reset emergency state");
  Serial.println("================================\n");
}

void loop() {
  // Reset watchdog timer
  esp_task_wdt_reset();
  
  // --- WiFi Reconnection Check ---
  wl_status_t wifiStatus = WiFi.status();
  
  if (wifiStatus == WL_CONNECTED) {
    if (!wifiConnected) {
      Serial.println("✅ WiFi Connected!");
      wifiConnected = true;
      uploadQueuedData();
    }
  } else {
    if (wifiConnected) {
      Serial.println("⚠️ WiFi Disconnected!");
      wifiConnected = false;
    }
    
    // Only attempt reconnection if not already connecting and interval passed
    if (wifiStatus != WL_IDLE_STATUS && 
        wifiStatus != WL_DISCONNECTED &&
        millis() - lastWiFiCheck >= WIFI_RECONNECT_INTERVAL) {
      // WiFi is in a failed state, try reconnecting
      lastWiFiCheck = millis();
      Serial.println("Attempting WiFi reconnection...");
      WiFi.disconnect(true); // true = also turn off WiFi
      delay(100);
      WiFi.begin(ssid, password);
    } else if (wifiStatus == WL_DISCONNECTED && 
               millis() - lastWiFiCheck >= WIFI_RECONNECT_INTERVAL) {
      // WiFi was disconnected, try reconnecting
      lastWiFiCheck = millis();
      Serial.println("Attempting WiFi reconnection...");
      WiFi.begin(ssid, password);
    }
  }

  // --- A. Continuous Sensor Reading ---
  long irValue = particleSensor.getIR();
  long redValue = particleSensor.getRed();
  
  // Check if finger is on sensor
  bool fingerDetected = (irValue > 50000);
  
  // Reset readings when finger is removed and placed back
  if (!fingerDetected && wasFingerDetected) {
    // Finger was just removed - reset all buffers
    Serial.println("Finger removed - resetting readings...");
    for (byte i = 0; i < RATE_SIZE; i++) rates[i] = 0;
    rateSpot = 0;
    validBeatCount = 0;
    beatAvg = 0;
    lastValidHR = 0;
    lastValidSpO2 = 0;
    lastBeat = 0;
  }
  wasFingerDetected = fingerDetected;
  
  // Heart Rate Detection with improved filtering
  if (fingerDetected && checkForBeat(irValue) == true) {
    long delta = millis() - lastBeat;
    lastBeat = millis();
    beatsPerMinute = 60 / (delta / 1000.0);
    
    // More strict filtering: normal resting HR is 60-100, exercise up to 180
    if (beatsPerMinute >= 40 && beatsPerMinute <= 180) {
      rates[rateSpot++] = (byte)beatsPerMinute;
      rateSpot %= RATE_SIZE;
      
      if (validBeatCount < RATE_SIZE) validBeatCount++;
      
      // Calculate average only from valid readings
      beatAvg = 0;
      for (byte x = 0; x < validBeatCount; x++) beatAvg += rates[x];
      beatAvg /= validBeatCount;
      
      lastValidHR = (float)beatAvg;
    }
  }
  
  // SpO2 Calculation - NON-BLOCKING incremental collection
  if (fingerDetected) {
    // Start collection every SPO2_CALC_INTERVAL
    if (!spo2CollectionActive && (millis() - lastSpO2Calc >= SPO2_CALC_INTERVAL)) {
      spo2CollectionActive = true;
      spo2SampleIndex = 0;
      lastSpo2Sample = millis();
    }
    
    // Collect samples incrementally (non-blocking)
    if (spo2CollectionActive && (millis() - lastSpo2Sample >= SPO2_SAMPLE_INTERVAL)) {
      lastSpo2Sample = millis();
      
      if (particleSensor.available()) {
        redBuffer[spo2SampleIndex] = particleSensor.getRed();
        irBuffer[spo2SampleIndex] = particleSensor.getIR();
        particleSensor.nextSample();
        spo2SampleIndex++;
        
        // All samples collected - calculate SpO2
        if (spo2SampleIndex >= BUFFER_LENGTH) {
          spo2CollectionActive = false;
          lastSpO2Calc = millis();
          
          // Calculate SpO2 and Heart Rate using the algorithm
          maxim_heart_rate_and_oxygen_saturation(irBuffer, BUFFER_LENGTH, redBuffer, 
                                                  &spo2Value, &validSPO2, 
                                                  &heartRateValue, &validHeartRate);
          
          if (validSPO2 && spo2Value >= 70 && spo2Value <= 100) {
            lastValidSpO2 = (float)spo2Value;
          }
          
          // Use algorithm's HR if valid and our beat detection doesn't have enough samples
          if (validHeartRate && heartRateValue >= 40 && heartRateValue <= 180 && validBeatCount < 4) {
            lastValidHR = (float)heartRateValue;
          }
        }
      } else {
        particleSensor.check();
      }
    }
  } else {
    // Reset SpO2 collection if finger removed
    spo2CollectionActive = false;
    spo2SampleIndex = 0;
  }
  
  // Use last valid readings, or 0 if no finger detected
  float currentSpO2 = fingerDetected ? lastValidSpO2 : 0.0;
  float currentHR = fingerDetected ? lastValidHR : 0.0;

  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);
  float accelMag = sqrt(sq(a.acceleration.x) + sq(a.acceleration.y) + sq(a.acceleration.z));
  float gyroMag = sqrt(sq(g.gyro.x) + sq(g.gyro.y) + sq(g.gyro.z));

  // --- B. Edge Intelligence: Anomaly Detection ---
  
  // 1. Fall Detection with confirmation delay and post-fall stillness
  if (accelMag > ACCEL_FALL_THRESH && gyroMag > GYRO_FALL_THRESH) {
    if (!fallPending && !emergencyActive && !emergencyHandled) {
      // Initial fall impact detected - start confirmation timer
      fallPending = true;
      fallDetectedTime = millis();
      Serial.println("⚠️ Potential fall detected - confirming...");
    }
  }
  
  // Confirm fall after delay if user is now still (post-fall stillness)
  if (fallPending && (millis() - fallDetectedTime >= FALL_CONFIRM_DELAY)) {
    // Check for post-fall stillness (low movement indicates user may be unconscious)
    if (accelMag < POST_FALL_STILLNESS_THRESH) {
      // Confirmed fall - user had impact and is now still
      fallPending = false;
      if (!emergencyActive && !emergencyHandled) {
        Serial.println("⚠️ FALL CONFIRMED! User is still. Triggering Emergency...");
        triggerEmergency("FALL DETECTED! User may be unresponsive.");
        
        // IMMEDIATE CLOUD UPLOAD OF CRITICAL DATA
        Serial.println("Uploading Emergency Data to Cloud...");
        sendDataToCloud(currentHR, currentSpO2, a, g);
      }
    } else {
      // User is moving - probably a false positive (e.g., caught themselves)
      fallPending = false;
      Serial.println("✅ Fall not confirmed - user is moving normally.");
    }
  }
  
  // Reset fall pending if too much time has passed (1 second timeout)
  if (fallPending && (millis() - fallDetectedTime > 1000)) {
    fallPending = false;
    Serial.println("Fall detection timeout - resetting.");
  }

  // 2. Physiological Anomaly (Mini Decision Tree)
  // ONLY check vitals if finger is detected AND we have valid readings
  if (fingerDetected && validBeatCount >= 4) {
    bool hrEmergency = (currentHR > HR_HIGH_THRESH) || (currentHR > 0 && currentHR < HR_LOW_THRESH);
    bool spo2Emergency = (currentSpO2 > 0 && currentSpO2 < SPO2_LOW_THRESH);
    
    if (hrEmergency || spo2Emergency) {
      if (!emergencyActive && !emergencyHandled) {
        Serial.println("⚠️ VITAL SIGN ALERT! Triggering Emergency...");
        triggerEmergency("CRITICAL VITALS ALERT! HR: " + String(currentHR) + ", SpO2: " + String(currentSpO2));
        
        // IMMEDIATE CLOUD UPLOAD OF CRITICAL DATA
        Serial.println("Uploading Emergency Data to Cloud...");
        sendDataToCloud(currentHR, currentSpO2, a, g);
      }
    }
  }

  // --- C. Emergency Handling Loop ---
  if (emergencyActive && !emergencyHandled) {
    handleEmergencyCalls();
  }
  
  // --- D. Check for Incoming SMS (Stop/Resume Condition) ---
  checkForIncomingSMS();
  
  // --- D2. Check for Manual Emergency Trigger ---
  checkManualEmergencyTrigger(currentHR, currentSpO2, a, g);

  // --- E. Periodic Cloud Transmission (Every 2 mins) ---
  unsigned long currentMillis = millis();
  if (currentMillis - previousMillis >= DATA_INTERVAL) {
    previousMillis = currentMillis;
    // We assume if an emergency happened recently, data was just sent, 
    // but sending again on schedule is fine/redundant.
    sendDataToCloud(currentHR, currentSpO2, a, g);
  }
}

// --- CLOUD FUNCTION ---
void sendDataToCloud(float hr, float spo2, sensors_event_t a, sensors_event_t g) {
  // Build JSON payload
  StaticJsonDocument<400> doc;
  doc["device_id"] = deviceId;
  doc["heart_rate"] = hr;
  doc["spo2"] = spo2;
  doc["accel_x"] = a.acceleration.x;
  doc["accel_y"] = a.acceleration.y;
  doc["accel_z"] = a.acceleration.z;
  doc["gyro_x"] = g.gyro.x;
  doc["gyro_y"] = g.gyro.y;
  doc["gyro_z"] = g.gyro.z;
  doc["timestamp"] = millis();
  doc["gps_lat"] = 0.0;
  doc["gps_long"] = 0.0;

  String jsonPayload;
  serializeJson(doc, jsonPayload);
  
  // Try WiFi first
  if (WiFi.status() == WL_CONNECTED) {
    if (sendDataViaWiFi(jsonPayload)) {
      return; // Success
    }
  }
  
  // Fallback to GSM/GPRS
  Serial.println("WiFi failed/unavailable - trying GSM...");
  if (sendDataViaGSM(jsonPayload)) {
    return; // Success
  }
  
  // Both failed - queue data
  Serial.println("All upload methods failed - queuing data");
  queueData(hr, spo2, a, g);
}

// Send data via WiFi HTTP
bool sendDataViaWiFi(String jsonPayload) {
  if (WiFi.status() != WL_CONNECTED) return false;
  
  HTTPClient http;
  http.begin(serverUrl);
  http.setTimeout(HTTP_TIMEOUT);
  http.addHeader("Content-Type", "application/json");
  
  int responseCode = -1;
  for (int attempt = 1; attempt <= MAX_UPLOAD_RETRIES; attempt++) {
    responseCode = http.POST(jsonPayload);
    if (responseCode > 0) {
      Serial.println("WiFi Upload Success: " + String(responseCode));
      http.end();
      return true;
    }
    Serial.println("WiFi attempt " + String(attempt) + " failed: " + http.errorToString(responseCode));
    if (attempt < MAX_UPLOAD_RETRIES) delay(1000);
  }
  
  http.end();
  return false;
}

// Send data via GSM/GPRS HTTP
bool sendDataViaGSM(String jsonPayload) {
  Serial.println("Sending data via GSM/GPRS...");
  
  // Initialize GPRS if not connected
  if (!gprsConnected) {
    if (!initGPRS()) {
      Serial.println("GPRS initialization failed");
      return false;
    }
  }
  
  // Start HTTP session
  if (!sendATCommand("AT+HTTPINIT", "OK", 2000)) {
    // HTTP might already be initialized, try to terminate and reinit
    sendATCommand("AT+HTTPTERM", "OK", 1000);
    if (!sendATCommand("AT+HTTPINIT", "OK", 2000)) {
      Serial.println("HTTP init failed");
      return false;
    }
  }
  
  // Set HTTP parameters
  sendATCommand("AT+HTTPPARA=\"CID\",1", "OK", 1000);
  
  // Set URL
  String urlCmd = "AT+HTTPPARA=\"URL\",\"" + String(serverUrl) + "\"";
  if (!sendATCommand(urlCmd, "OK", 2000)) {
    sendATCommand("AT+HTTPTERM", "OK", 1000);
    return false;
  }
  
  // Set content type
  sendATCommand("AT+HTTPPARA=\"CONTENT\",\"application/json\"", "OK", 1000);
  
  // Set data to send
  String dataCmd = "AT+HTTPDATA=" + String(jsonPayload.length()) + ",10000";
  gsmSerial.println(dataCmd);
  delay(500);
  
  // Wait for DOWNLOAD prompt
  unsigned long startTime = millis();
  bool downloadPrompt = false;
  while (millis() - startTime < 3000) {
    if (gsmSerial.available()) {
      String resp = gsmSerial.readString();
      if (resp.indexOf("DOWNLOAD") != -1) {
        downloadPrompt = true;
        break;
      }
    }
  }
  
  if (!downloadPrompt) {
    Serial.println("HTTPDATA prompt failed");
    sendATCommand("AT+HTTPTERM", "OK", 1000);
    return false;
  }
  
  // Send the JSON payload
  gsmSerial.print(jsonPayload);
  delay(1000);
  
  // Execute HTTP POST
  gsmSerial.println("AT+HTTPACTION=1"); // 1 = POST
  
  // Wait for response (up to 30 seconds)
  startTime = millis();
  bool success = false;
  while (millis() - startTime < 30000) {
    if (gsmSerial.available()) {
      String resp = gsmSerial.readString();
      Serial.println("GSM Response: " + resp);
      
      // +HTTPACTION: 1,200,xxx means success (200 OK)
      if (resp.indexOf("+HTTPACTION:") != -1) {
        if (resp.indexOf(",200,") != -1 || resp.indexOf(",201,") != -1) {
          Serial.println("GSM Upload Success!");
          success = true;
        } else {
          Serial.println("GSM Upload Failed - Server Error");
        }
        break;
      }
    }
    delay(100);
  }
  
  // Terminate HTTP session
  sendATCommand("AT+HTTPTERM", "OK", 1000);
  
  return success;
}

// Initialize GPRS connection
bool initGPRS() {
  Serial.println("Initializing GPRS...");
  
  // Check if already attached to GPRS
  gsmSerial.println("AT+CGATT?");
  delay(1000);
  String resp = "";
  while (gsmSerial.available()) {
    resp += (char)gsmSerial.read();
  }
  
  // Attach to GPRS if not attached
  if (resp.indexOf("+CGATT: 0") != -1) {
    if (!sendATCommand("AT+CGATT=1", "OK", 10000)) {
      Serial.println("GPRS attach failed");
      return false;
    }
  }
  
  // Set bearer profile - Connection type GPRS
  sendATCommand("AT+SAPBR=3,1,\"CONTYPE\",\"GPRS\"", "OK", 2000);
  
  // Set APN
  String apnCmd = "AT+SAPBR=3,1,\"APN\",\"" + String(gsmApn) + "\"";
  sendATCommand(apnCmd, "OK", 2000);
  
  // Set APN username if provided
  if (strlen(gsmUser) > 0) {
    String userCmd = "AT+SAPBR=3,1,\"USER\",\"" + String(gsmUser) + "\"";
    sendATCommand(userCmd, "OK", 2000);
  }
  
  // Set APN password if provided
  if (strlen(gsmPass) > 0) {
    String passCmd = "AT+SAPBR=3,1,\"PWD\",\"" + String(gsmPass) + "\"";
    sendATCommand(passCmd, "OK", 2000);
  }
  
  // Open bearer
  if (!sendATCommand("AT+SAPBR=1,1", "OK", 15000)) {
    // May already be open
    gsmSerial.println("AT+SAPBR=2,1");
    delay(2000);
    resp = "";
    while (gsmSerial.available()) {
      resp += (char)gsmSerial.read();
    }
    if (resp.indexOf("+SAPBR: 1,1") == -1) {
      Serial.println("Bearer open failed");
      return false;
    }
  }
  
  gprsConnected = true;
  Serial.println("GPRS Connected!");
  return true;
}

// Close GPRS connection
void closeGPRS() {
  sendATCommand("AT+SAPBR=0,1", "OK", 5000);
  gprsConnected = false;
  Serial.println("GPRS Disconnected");
}

// Queue data for later upload when offline
void queueData(float hr, float spo2, sensors_event_t a, sensors_event_t g) {
  dataQueue[queueHead].hr = hr;
  dataQueue[queueHead].spo2 = spo2;
  dataQueue[queueHead].accel_x = a.acceleration.x;
  dataQueue[queueHead].accel_y = a.acceleration.y;
  dataQueue[queueHead].accel_z = a.acceleration.z;
  dataQueue[queueHead].gyro_x = g.gyro.x;
  dataQueue[queueHead].gyro_y = g.gyro.y;
  dataQueue[queueHead].gyro_z = g.gyro.z;
  dataQueue[queueHead].pending = true;
  
  queueHead = (queueHead + 1) % DATA_QUEUE_SIZE;
  Serial.println("Data queued. Queue position: " + String(queueHead));
}

// Upload queued data when connection available
void uploadQueuedData() {
  Serial.println("Checking for queued data...");
  int uploaded = 0;
  
  for (int i = 0; i < DATA_QUEUE_SIZE; i++) {
    if (dataQueue[i].pending) {
      StaticJsonDocument<400> doc;
      doc["device_id"] = deviceId;
      doc["heart_rate"] = dataQueue[i].hr;
      doc["spo2"] = dataQueue[i].spo2;
      doc["accel_x"] = dataQueue[i].accel_x;
      doc["accel_y"] = dataQueue[i].accel_y;
      doc["accel_z"] = dataQueue[i].accel_z;
      doc["gyro_x"] = dataQueue[i].gyro_x;
      doc["gyro_y"] = dataQueue[i].gyro_y;
      doc["gyro_z"] = dataQueue[i].gyro_z;
      doc["queued"] = true;
      doc["gps_lat"] = 0.0;
      doc["gps_long"] = 0.0;
      
      String jsonPayload;
      serializeJson(doc, jsonPayload);
      
      bool success = false;
      
      // Try WiFi first
      if (WiFi.status() == WL_CONNECTED) {
        success = sendDataViaWiFi(jsonPayload);
      }
      
      // Fallback to GSM
      if (!success) {
        success = sendDataViaGSM(jsonPayload);
      }
      
      if (success) {
        dataQueue[i].pending = false;
        uploaded++;
      }
      
      delay(100);
    }
  }
  
  if (uploaded > 0) {
    Serial.println("Uploaded " + String(uploaded) + " queued records");
  }
}

// --- MANUAL EMERGENCY TRIGGER ---
unsigned long buttonPressStart = 0;
bool buttonPressed = false;

void checkManualEmergencyTrigger(float currentHR, float currentSpO2, sensors_event_t a, sensors_event_t g) {
  // Check Serial Monitor for commands
  if (Serial.available()) {
    char cmd = Serial.read();
    
    // Clear remaining buffer
    while (Serial.available()) Serial.read();
    
    if (cmd == 'E' || cmd == 'e') {
      Serial.println("\n🚨 MANUAL EMERGENCY TRIGGERED VIA SERIAL!");
      triggerManualEmergency(currentHR, currentSpO2, a, g);
    }
    else if (cmd == 'R' || cmd == 'r') {
      Serial.println("\n✅ Emergency state RESET. Ready for new emergency.");
      emergencyActive = false;
      emergencyHandled = false;
    }
    else if (cmd == 'S' || cmd == 's') {
      // Status command
      Serial.println("\n=== SYSTEM STATUS ===");
      Serial.println("Emergency Active: " + String(emergencyActive ? "YES" : "NO"));
      Serial.println("Emergency Handled: " + String(emergencyHandled ? "YES" : "NO"));
      Serial.println("WiFi Connected: " + String(wifiConnected ? "YES" : "NO"));
      Serial.println("GPRS Connected: " + String(gprsConnected ? "YES" : "NO"));
      Serial.println("Current HR: " + String(currentHR));
      Serial.println("Current SpO2: " + String(currentSpO2));
      Serial.println("===================\n");
    }
  }
  
  // Check physical button (GPIO0 / BOOT button)
  if (digitalRead(EMERGENCY_BUTTON_PIN) == LOW) {
    if (!buttonPressed) {
      buttonPressed = true;
      buttonPressStart = millis();
    }
    // Check for long press (2 seconds)
    if (millis() - buttonPressStart >= 2000) {
      Serial.println("\n🚨 MANUAL EMERGENCY TRIGGERED VIA BUTTON!");
      triggerManualEmergency(currentHR, currentSpO2, a, g);
      buttonPressed = false; // Reset to prevent repeated triggers
      delay(1000); // Debounce
    }
  } else {
    buttonPressed = false;
  }
}

void triggerManualEmergency(float currentHR, float currentSpO2, sensors_event_t a, sensors_event_t g) {
  // Reset emergency state first to allow triggering even if previously handled
  emergencyActive = false;
  emergencyHandled = false;
  
  // Create test data if no valid readings
  float testHR = (currentHR > 0) ? currentHR : 75.0;  // Use real or test HR
  float testSpO2 = (currentSpO2 > 0) ? currentSpO2 : 98.0;  // Use real or test SpO2
  
  Serial.println("=== EMERGENCY TEST DATA ===");
  Serial.println("HR: " + String(testHR));
  Serial.println("SpO2: " + String(testSpO2));
  Serial.println("Accel X: " + String(a.acceleration.x));
  Serial.println("Accel Y: " + String(a.acceleration.y));
  Serial.println("Accel Z: " + String(a.acceleration.z));
  Serial.println("===========================");
  
  // 1. Upload emergency data to cloud
  Serial.println("\n[1/3] Uploading Emergency Data to Cloud...");
  sendEmergencyDataToCloud(testHR, testSpO2, a, g);
  
  // 2. Trigger emergency (sends SMS)
  Serial.println("\n[2/3] Sending Emergency SMS...");
  triggerEmergency("MANUAL EMERGENCY TEST! HR: " + String(testHR) + ", SpO2: " + String(testSpO2));
  
  // 3. Emergency calls will be handled by the main loop
  Serial.println("\n[3/3] Emergency calls will start automatically...");
  Serial.println("Send 'R' to stop emergency sequence\n");
}

void sendEmergencyDataToCloud(float hr, float spo2, sensors_event_t a, sensors_event_t g) {
  StaticJsonDocument<400> doc;
  doc["device_id"] = deviceId;
  doc["heart_rate"] = hr;
  doc["spo2"] = spo2;
  doc["accel_x"] = a.acceleration.x;
  doc["accel_y"] = a.acceleration.y;
  doc["accel_z"] = a.acceleration.z;
  doc["gyro_x"] = g.gyro.x;
  doc["gyro_y"] = g.gyro.y;
  doc["gyro_z"] = g.gyro.z;
  doc["timestamp"] = millis();
  doc["emergency"] = true;  // Mark as emergency data
  doc["manual_trigger"] = true;  // Mark as manually triggered
  doc["gps_lat"] = 0.0;
  doc["gps_long"] = 0.0;

  String jsonPayload;
  serializeJson(doc, jsonPayload);
  
  Serial.println("Payload: " + jsonPayload);
  
  // Try WiFi first
  if (WiFi.status() == WL_CONNECTED) {
    if (sendDataViaWiFi(jsonPayload)) {
      Serial.println("✅ Emergency data uploaded via WiFi");
      return;
    }
  }
  
  // Fallback to GSM
  Serial.println("Trying GSM upload...");
  if (sendDataViaGSM(jsonPayload)) {
    Serial.println("✅ Emergency data uploaded via GSM");
    return;
  }
  
  Serial.println("❌ Emergency data upload failed - queued for later");
}

// --- EMERGENCY FUNCTIONS ---
void triggerEmergency(String msg) {
  if (emergencyActive || emergencyHandled) return; // Don't trigger if active or already handled
  
  emergencyActive = true;
  emergencyHandled = false; // New emergency, so it's not handled yet
  
  // 1. Send SMS immediately (Only once per emergency event)
  sendSMS(EMERGENCY_PHONE, msg);
  
  // 2. Start calling loop immediately
  lastCallTime = millis() - CALL_INTERVAL; // Force immediate first call
}

void handleEmergencyCalls() {
  if (!emergencyActive || emergencyHandled) return;

  if (millis() - lastCallTime >= CALL_INTERVAL) {
    lastCallTime = millis();
    Serial.println("Dialing Emergency Contact...");
    
    gsmSerial.print("ATD");
    gsmSerial.print(EMERGENCY_PHONE);
    gsmSerial.println(";");
    
    // Monitor call status for pick-up/decline logic
    unsigned long callStart = millis();
    bool callAnswered = false;
    
    // Wait for 25 seconds for the call to be answered
    while (millis() - callStart < 25000) { 
      
      // *** CRITICAL FIX: Check for SMS *inside* the waiting loop ***
      checkForIncomingSMS();
      if (emergencyHandled) {
          Serial.println("Emergency Handled via SMS! Cancelling call...");
          gsmSerial.println("ATH"); // Hang up immediately
          return; // Exit function
      }

      // Check call status
      gsmSerial.println("AT+CLCC");
      delay(500); 
      if (gsmSerial.available()) {
        String resp = gsmSerial.readString();
        // Status 0: Active (Answered)
        if (resp.indexOf("+CLCC: 1,0,0,0,0") != -1) { 
           Serial.println("Call Answered! Emergency Acknowledged.");
           gsmSerial.println("ATH"); 
           emergencyActive = false; 
           emergencyHandled = true; 
           callAnswered = true;
           break; 
        }
      }
    }
    
    // If loop finished and call wasn't answered
    if (!callAnswered && !emergencyHandled) { 
       if(emergencyActive) {
           Serial.println("Call ignored/missed. Will retry in 30s.");
           gsmSerial.println("ATH"); // Ensure line is clear
       }
    }
  }
}

void checkForIncomingSMS() {
  // Check if there is data available from the GSM module
  if (gsmSerial.available()) {
    String data = gsmSerial.readString();
    
    // Check if it's an incoming SMS notification (+CMTI) or if it's the message content itself
    // Depending on mode (CNMI settings), the message might come directly.
    // Here we handle the +CMTI notification which says a message is stored at index X.
    
    if (data.indexOf("+CMTI:") != -1) {
      Serial.println("New SMS Notification Received");
      // Extract index to read the message
      int indexStrStart = data.indexOf(","); 
      String indexStr = data.substring(indexStrStart + 1);
      int index = indexStr.toInt();
      
      // Read the SMS content
      gsmSerial.print("AT+CMGR=");
      gsmSerial.println(index);
      delay(500);
      
      // Read the response (Content of the SMS)
      String smsContent = "";
      while (gsmSerial.available()) {
          smsContent += (char)gsmSerial.read();
      }
      
      Serial.println("Received SMS Content: " + smsContent);

      // Check if the message contains "OK" (case-insensitive)
      if (smsContent.indexOf("OK") != -1 || smsContent.indexOf("ok") != -1) {
        Serial.println("✅ Received 'OK'. Stopping Emergency Alert Sequence.");
        emergencyActive = false;
        emergencyHandled = true;
        
        // Optional: Send confirmation back
        sendSMS(EMERGENCY_PHONE, "Alert acknowledged. Calls stopped.");
      }
      // Check if the message contains "Resume" (case-insensitive)
      else if (smsContent.indexOf("Resume") != -1 || smsContent.indexOf("resume") != -1) {
        Serial.println("✅ Received 'Resume'. Resuming Emergency Alert Sequence.");
        emergencyActive = true;
        emergencyHandled = false;
        
        // Optional: Send confirmation back
        sendSMS(EMERGENCY_PHONE, "Alert sequence resumed. Calls restarting.");
      }
      
      // Optional: Delete message to keep memory clean
      gsmSerial.print("AT+CMGD="); gsmSerial.println(index);
    } 
    // Sometimes the message content comes directly if we are reading it
    else if (data.indexOf("OK") != -1 || data.indexOf("ok") != -1) {
         // This is a bit risky as "OK" is a standard AT response, 
         // but if it's part of an SMS read (+CMGR), it might appear. 
         // Sticking to the +CMTI logic is safer for now.
    }
  }
}

// Helper to send SMS with verification
bool sendSMS(String num, String msg) {
  Serial.println("Sending SMS to " + num + "...");
  
  gsmSerial.print("AT+CMGS=\""); 
  gsmSerial.print(num); 
  gsmSerial.println("\"");
  delay(1000);
  
  // Check for '>' prompt
  unsigned long startTime = millis();
  bool promptReceived = false;
  while (millis() - startTime < 3000) {
    if (gsmSerial.available()) {
      char c = gsmSerial.read();
      if (c == '>') {
        promptReceived = true;
        break;
      }
    }
  }
  
  if (!promptReceived) {
    Serial.println("❌ SMS prompt not received");
    gsmSerial.write(27); // ESC to cancel
    return false;
  }
  
  gsmSerial.print(msg);
  delay(100);
  gsmSerial.write(26); // CTRL+Z to send
  
  // Wait for confirmation
  startTime = millis();
  String response = "";
  while (millis() - startTime < 10000) {
    if (gsmSerial.available()) {
      response += (char)gsmSerial.read();
    }
    if (response.indexOf("+CMGS:") != -1) {
      Serial.println("✅ SMS Sent Successfully");
      return true;
    }
    if (response.indexOf("ERROR") != -1) {
      Serial.println("❌ SMS Send Failed");
      return false;
    }
  }
  
  Serial.println("⚠️ SMS status unknown (timeout)");
  return false;
}

// Check GSM module connection status
bool checkGSMStatus() {
  gsmSerial.println("AT");
  delay(500);
  
  String response = "";
  unsigned long startTime = millis();
  while (millis() - startTime < 2000) {
    if (gsmSerial.available()) {
      response += (char)gsmSerial.read();
    }
  }
  
  return (response.indexOf("OK") != -1);
}

// Improved AT command with response validation
bool sendATCommand(String cmd, String expected, unsigned long timeout) {
  // Clear any pending data
  while (gsmSerial.available()) {
    gsmSerial.read();
  }
  
  gsmSerial.println(cmd);
  
  String response = "";
  unsigned long startTime = millis();
  while (millis() - startTime < timeout) {
    if (gsmSerial.available()) {
      response += (char)gsmSerial.read();
    }
    if (response.indexOf(expected) != -1) {
      Serial.println("AT OK: " + cmd);
      return true;
    }
    if (response.indexOf("ERROR") != -1) {
      Serial.println("AT ERROR: " + cmd);
      return false;
    }
  }
  
  Serial.println("AT TIMEOUT: " + cmd);
  return false;
}