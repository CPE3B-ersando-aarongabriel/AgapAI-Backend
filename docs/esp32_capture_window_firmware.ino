#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <time.h>
#include <math.h>
#include <driver/i2s.h>

#if __has_include(<esp_arduino_version.h>)
#include <esp_arduino_version.h>
#endif

#ifndef ESP_ARDUINO_VERSION_MAJOR
#define ESP_ARDUINO_VERSION_MAJOR 2
#endif

// =========================
// User Config
// =========================
const char* WIFI_SSID = "TendahanNiHosebo";
const char* WIFI_PASSWORD = "ussnimitz1825!";

const char* API_BASE = "https://agapai-backend.onrender.com/";
const char* DEVICE_ID = "esp32-dev-001";
const char* FW_VERSION = "esp32-streaming-v1";

// If true, read real presence from LD2410 OUT pin.
// If false, infer presence from mic activity.
const bool USE_REAL_LD2410_OUT = true;

// =========================
// Hardware Pins (unchanged)
// =========================
#define DHTPIN 4
#define DHTTYPE DHT22

#define BUTTON_PIN 14
#define LD2410_OUT_PIN 27

// OLED SPI (6-pin module, no CS)
#define OLED_SCLK 18
#define OLED_MOSI 23
#define OLED_DC 16
#define OLED_RST 17
#define OLED_CS -1

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

// INMP441 I2S
#define I2S_PORT I2S_NUM_0
#define I2S_WS 25
#define I2S_SCK 26
#define I2S_SD 33

// =========================
// Timing / Runtime
// =========================
const uint32_t SAMPLE_INTERVAL_MS = 1200;
const uint32_t WIFI_CONNECT_TIMEOUT_MS = 25000;
const uint32_t WIFI_RETRY_INTERVAL_MS = 4000;
const uint32_t BUTTON_DEBOUNCE_MS = 40;
const uint32_t HEARTBEAT_MS = 2000;
const uint32_t SNORE_THRESHOLD = 45;

const uint16_t HTTP_CONNECT_TIMEOUT_MS = 5000;
const uint16_t HTTP_TIMEOUT_MS = 8000;
const bool SERIAL_LOGS = true;

// Mic normalization targets: convert tiny linear PCM magnitudes into a stable 0-100 scale.
const float MIC_DB_MIN = -75.0f;
const float MIC_DB_MAX = -20.0f;
const uint8_t MIC_SILENT_REINIT_AFTER = 14;

enum DeviceState {
  STATE_IDLE,
  STATE_CAPTURING,
  STATE_SUBMITTING,
  STATE_RESULT,
  STATE_ERROR
};

struct SensorSample {
  uint64_t epoch_ms;
  float mic_raw;
  float mic_rms;
  float mic_peak;
  float temperature;
  float humidity;
  float breathing_rate;
  float movement_level;
  bool presence_detected;
};

struct RollingStats {
  uint32_t sample_count;
  double sum_mic_raw;
  double sum_mic_rms;
  float max_mic_peak;
  uint32_t snore_event_count;
  double sum_breathing_rate;
  double sum_temperature;
  double sum_humidity;
};

DHT dht(DHTPIN, DHTTYPE);
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &SPI, OLED_DC, OLED_RST, OLED_CS);

DeviceState currentState = STATE_IDLE;
bool oledReady = false;
String currentSessionId = "";
RollingStats stats = {};

// Keep a tiny retry queue so temporary network drops do not lose samples.
const uint8_t PENDING_QUEUE_CAPACITY = 20;
SensorSample pendingQueue[PENDING_QUEUE_CAPACITY];
uint8_t pendingCount = 0;

// Auto-select active I2S channel (0=left, 1=right) to avoid silent-channel setups.
int activeMicChannel = -1;
int activeMicDecode = -1;
uint8_t micSilentStreak = 0;

float lastValidTemp = 25.0f;
float lastValidHum = 50.0f;
uint32_t lastDhtWarnMs = 0;

String latestRecommendation = "";
String latestBreathingLine = "";

bool buttonLastRawState = HIGH;
bool buttonStableState = HIGH;
uint32_t lastDebounceMs = 0;
uint32_t lastButtonPollLogMs = 0;

uint32_t lastSampleMs = 0;
uint32_t lastHeartbeatMs = 0;
uint32_t lastWiFiAttemptMs = 0;

// =========================
// Utility
// =========================
const char* stateName(DeviceState s) {
  switch (s) {
    case STATE_IDLE: return "IDLE";
    case STATE_CAPTURING: return "CAPTURING";
    case STATE_SUBMITTING: return "SUBMITTING";
    case STATE_RESULT: return "RESULT";
    case STATE_ERROR: return "ERROR";
    default: return "UNKNOWN";
  }
}

void logLine(const String& msg) {
  if (SERIAL_LOGS) {
    Serial.println(msg);
  }
}

void setState(DeviceState next) {
  if (currentState != next) {
    logLine(String("[STATE] ") + stateName(currentState) + " -> " + stateName(next));
  }
  currentState = next;
}

String baseUrlNormalized() {
  String b = String(API_BASE);
  while (b.endsWith("/")) {
    b.remove(b.length() - 1);
  }
  return b;
}

String endpointStart() {
  return baseUrlNormalized() + "/api/session/start";
}

String endpointChunk() {
  return baseUrlNormalized() + "/api/session/chunk";
}

String endpointEnd() {
  return baseUrlNormalized() + "/api/session/end";
}

uint64_t nowEpochMs() {
  struct timeval tv;
  gettimeofday(&tv, nullptr);
  return (uint64_t)tv.tv_sec * 1000ULL + (uint64_t)tv.tv_usec / 1000ULL;
}

String iso8601FromEpochMs(uint64_t epochMs) {
  time_t sec = (time_t)(epochMs / 1000ULL);
  struct tm tmUtc;
#if defined(ESP32)
  gmtime_r(&sec, &tmUtc);
#else
  tmUtc = *gmtime(&sec);
#endif

  char buf[32];
  snprintf(
    buf,
    sizeof(buf),
    "%04d-%02d-%02dT%02d:%02d:%02d.000Z",
    tmUtc.tm_year + 1900,
    tmUtc.tm_mon + 1,
    tmUtc.tm_mday,
    tmUtc.tm_hour,
    tmUtc.tm_min,
    tmUtc.tm_sec
  );
  return String(buf);
}

String clipText(const String& s, size_t maxLen = 21) {
  if (s.length() <= maxLen) return s;
  return s.substring(0, maxLen);
}

// =========================
// OLED
// =========================
void drawOled(const String& l1, const String& l2 = "", const String& l3 = "") {
  if (!oledReady) {
    logLine(String("[OLED] ") + l1 + (l2.length() ? " | " + l2 : "") + (l3.length() ? " | " + l3 : ""));
    return;
  }

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(l1);
  if (l2.length()) display.println(l2);
  if (l3.length()) display.println(l3);
  display.display();
}

void initOled() {
  SPI.begin(OLED_SCLK, -1, OLED_MOSI, -1);
  if (!display.begin(SSD1306_SWITCHCAPVCC)) {
    oledReady = false;
    logLine("[OLED] init failed");
    return;
  }
  oledReady = true;
  logLine("[OLED] SPI OLED ready");
  drawOled("AGAPAI", "SPI OLED ready");
}

// =========================
// WiFi / NTP
// =========================
bool connectWiFiBlocking(uint32_t timeoutMs = WIFI_CONNECT_TIMEOUT_MS) {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  logLine(String("[WIFI] Connecting to ") + WIFI_SSID);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < timeoutMs) {
    delay(300);
  }

  if (WiFi.status() == WL_CONNECTED) {
    logLine(String("[WIFI] Connected IP=") + WiFi.localIP().toString() + " RSSI=" + String(WiFi.RSSI()));
    drawOled("WiFi connected", WiFi.localIP().toString());
    return true;
  }

  logLine("[WIFI] Connect timeout");
  drawOled("WiFi failed");
  return false;
}

void ensureWiFiConnected() {
  if (WiFi.status() == WL_CONNECTED) return;

  uint32_t nowMs = millis();
  if ((nowMs - lastWiFiAttemptMs) < WIFI_RETRY_INTERVAL_MS) return;
  lastWiFiAttemptMs = nowMs;

  logLine("[WIFI] Reconnecting...");
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void syncNtpTime() {
  if (WiFi.status() != WL_CONNECTED) return;

  logLine("[NTP] Sync start");
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");

  time_t now = time(nullptr);
  uint8_t tries = 0;
  while (now < 1700000000 && tries < 25) {
    delay(250);
    now = time(nullptr);
    tries++;
  }

  if (now >= 1700000000) {
    logLine(String("[NTP] Sync OK epoch=") + String((uint32_t)now));
  } else {
    logLine("[NTP] Not ready, continuing");
  }
}

// =========================
// I2S Mic
// =========================
void initI2S() {
  logLine("[I2S] Initializing INMP441 interface");

  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = 16000;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;

#if ESP_ARDUINO_VERSION_MAJOR >= 3
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
#else
  cfg.communication_format = (i2s_comm_format_t)(I2S_COMM_FORMAT_I2S | I2S_COMM_FORMAT_I2S_MSB);
#endif

  cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count = 8;
  cfg.dma_buf_len = 256;
  cfg.use_apll = false;
  cfg.tx_desc_auto_clear = false;
  cfg.fixed_mclk = 0;

  i2s_pin_config_t pin = {};
  pin.mck_io_num = I2S_PIN_NO_CHANGE;
  pin.bck_io_num = I2S_SCK;
  pin.ws_io_num = I2S_WS;
  pin.data_out_num = I2S_PIN_NO_CHANGE;
  pin.data_in_num = I2S_SD;

  esp_err_t e = i2s_driver_install(I2S_PORT, &cfg, 0, NULL);
  if (e != ESP_OK) {
    logLine(String("[I2S] driver install error=") + String((int)e));
    return;
  }

  e = i2s_set_pin(I2S_PORT, &pin);
  if (e != ESP_OK) {
    logLine(String("[I2S] set pin error=") + String((int)e));
    return;
  }

  i2s_zero_dma_buffer(I2S_PORT);
  activeMicChannel = -1;
  activeMicDecode = -1;
  micSilentStreak = 0;
  logLine("[I2S] Ready");
}

float mapDbToScore(float dbfs) {
  float normalized = (dbfs - MIC_DB_MIN) / (MIC_DB_MAX - MIC_DB_MIN);
  if (normalized < 0.0f) normalized = 0.0f;
  if (normalized > 1.0f) normalized = 1.0f;
  return normalized * 100.0f;
}

int32_t signExtend24(uint32_t v) {
  if (v & 0x00800000UL) {
    v |= 0xFF000000UL;
  }
  return (int32_t)v;
}

void readMicMetrics(float& micRaw, float& micRms, float& micPeak) {
  const int N = 256;
  static int32_t buffer[N];
  size_t bytesRead = 0;

  esp_err_t rc = i2s_read(I2S_PORT, (void*)buffer, sizeof(buffer), &bytesRead, 20 / portTICK_PERIOD_MS);
  if (rc != ESP_OK || bytesRead == 0) {
    micRaw = 0.0f;
    micRms = 0.0f;
    micPeak = 0.0f;
    return;
  }

  int count = bytesRead / sizeof(int32_t);
  if (count <= 0) {
    micRaw = 0.0f;
    micRms = 0.0f;
    micPeak = 0.0f;
    return;
  }

  int frames = count / 2;
  if (frames <= 0) {
    micRaw = 0.0f;
    micRms = 0.0f;
    micPeak = 0.0f;
    return;
  }

  double sumAbs[6] = {0, 0, 0, 0, 0, 0};
  double sumSq[6] = {0, 0, 0, 0, 0, 0};
  double peak[6] = {0, 0, 0, 0, 0, 0};

  for (int i = 0; i < frames; i++) {
    int32_t rawL = buffer[2 * i];
    int32_t rawR = buffer[2 * i + 1];

    double candidates[6] = {
      (double)(rawL >> 8) / 8388608.0,                                  // left, high 24 bits
      (double)(rawR >> 8) / 8388608.0,                                  // right, high 24 bits
      (double)signExtend24((uint32_t)rawL & 0x00FFFFFFUL) / 8388608.0,  // left, low 24 bits
      (double)signExtend24((uint32_t)rawR & 0x00FFFFFFUL) / 8388608.0,  // right, low 24 bits
      (double)rawL / 2147483648.0,                                       // left, full 32-bit
      (double)rawR / 2147483648.0                                        // right, full 32-bit
    };

    for (int j = 0; j < 6; j++) {
      double x = candidates[j];
      double a = fabs(x);
      sumAbs[j] += a;
      sumSq[j] += x * x;
      if (a > peak[j]) peak[j] = a;
    }
  }

  float rmsCandidates[6];
  for (int j = 0; j < 6; j++) {
    rmsCandidates[j] = (float)sqrt(sumSq[j] / (double)frames);
  }

  int bestIdx = 0;
  for (int j = 1; j < 6; j++) {
    if (rmsCandidates[j] > rmsCandidates[bestIdx]) {
      bestIdx = j;
    }
  }

  if (bestIdx != activeMicDecode) {
    activeMicDecode = bestIdx;
    const char* decodeLabel =
      (bestIdx == 0) ? "L_hi24" :
      (bestIdx == 1) ? "R_hi24" :
      (bestIdx == 2) ? "L_lo24" :
      (bestIdx == 3) ? "R_lo24" :
      (bestIdx == 4) ? "L_i32" : "R_i32";
    activeMicChannel = (bestIdx % 2 == 0) ? 0 : 1;
    logLine(String("[I2S] decode -> ") + decodeLabel + " channel=" + (activeMicChannel == 0 ? "LEFT" : "RIGHT"));
  }

  double avgAbsLinear = sumAbs[bestIdx] / (double)frames;
  double rmsLinear = rmsCandidates[bestIdx];
  double peakLinear = peak[bestIdx];

  if (rmsLinear < 1e-9 && peakLinear < 1e-9) {
    micSilentStreak++;
  } else {
    micSilentStreak = 0;
  }

  if (micSilentStreak >= MIC_SILENT_REINIT_AFTER) {
    logLine("[I2S] sustained silence detected, restarting I2S");
    i2s_driver_uninstall(I2S_PORT);
    initI2S();
    micSilentStreak = 0;
  }

  float rawDb = 20.0f * log10f(fmaxf((float)avgAbsLinear, 1e-9f));
  float rmsDb = 20.0f * log10f(fmaxf((float)rmsLinear, 1e-9f));
  float peakDb = 20.0f * log10f(fmaxf((float)peakLinear, 1e-9f));

  micRaw = mapDbToScore(rawDb);
  micRms = mapDbToScore(rmsDb);
  micPeak = mapDbToScore(peakDb);

  if (SERIAL_LOGS) {
    logLine(
      String("[MIC] lin_rms=") + String((float)rmsLinear, 6) +
      " (" + String(rmsDb, 1) + " dBFS)" +
      " score_rms=" + String(micRms, 1) +
      " peak=" + String(micPeak, 1)
    );
  }

  if (micRaw < 0.0f) micRaw = 0.0f;
  if (micRms < 0.0f) micRms = 0.0f;
  if (micPeak < 0.0f) micPeak = 0.0f;
}

// =========================
// Sensor Derivations
// =========================
bool readPresence(float micRaw) {
  if (USE_REAL_LD2410_OUT) {
    return digitalRead(LD2410_OUT_PIN) == HIGH;
  }
  return micRaw > 8.0f;
}

float estimateMovement(bool presence, float micPeak) {
  if (!presence) return 0.0f;
  float movement = micPeak * 0.8f;
  if (movement > 100.0f) movement = 100.0f;
  return movement;
}

float estimateBreathingRate(bool presence, float micRaw) {
  if (!presence) return 0.0f;
  float br = 12.0f + fminf(8.0f, micRaw * 0.1f);
  if (br < 8.0f) br = 8.0f;
  if (br > 24.0f) br = 24.0f;
  return br;
}

// =========================
// HTTP
// =========================
bool postJsonWithRetry(const String& url, const String& body, String& responseOut, int& codeOut, uint8_t maxAttempts) {
  for (uint8_t attempt = 1; attempt <= maxAttempts; attempt++) {
    if (WiFi.status() != WL_CONNECTED) {
      ensureWiFiConnected();
      delay(250);
    }

    WiFiClientSecure client;
    client.setInsecure();
    client.setTimeout(HTTP_TIMEOUT_MS / 1000);

    HTTPClient http;
    http.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
    http.setTimeout(HTTP_TIMEOUT_MS);
    http.setReuse(false);

    logLine(String("[HTTP] Attempt ") + String(attempt) + "/" + String(maxAttempts));
    logLine(String("[HTTP] POST ") + url);
    logLine(String("[HTTP] Body bytes=") + String(body.length()));

    if (!http.begin(client, url)) {
      codeOut = -1;
      logLine("[HTTP] begin() failed");
    } else {
      http.addHeader("Content-Type", "application/json");
      http.addHeader("Connection", "close");
      int code = http.POST(body);
      codeOut = code;

      if (code > 0) {
        responseOut = http.getString();
      } else {
        logLine(String("[HTTP] POST failed: ") + http.errorToString(code));
      }
      logLine(String("[HTTP] Status=") + String(code));

      if (responseOut.length() > 0) {
        size_t n = responseOut.length();
        if (n > 220) n = 220;
        logLine(String("[HTTP] Resp preview: ") + responseOut.substring(0, n));
      }

      http.end();
      if (code >= 200 && code < 300) {
        return true;
      }
    }

    if (attempt < maxAttempts) {
      delay(700U * attempt);
    }
  }

  return false;
}

// =========================
// Session API
// =========================
bool parseSessionId(const String& response, String& sessionIdOut) {
  StaticJsonDocument<768> doc;
  DeserializationError err = deserializeJson(doc, response);
  if (err) {
    logLine(String("[SESSION] parse error: ") + err.c_str());
    return false;
  }

  if (!doc["session_id"].is<const char*>()) {
    logLine("[SESSION] response missing session_id");
    return false;
  }

  sessionIdOut = String((const char*)doc["session_id"]);
  return sessionIdOut.length() > 0;
}

bool startSession() {
  if (WiFi.status() != WL_CONNECTED) {
    logLine("[SESSION] start aborted: wifi down");
    return false;
  }

  StaticJsonDocument<512> req;
  req["device_id"] = DEVICE_ID;
  req["firmware_version"] = FW_VERSION;
  JsonObject metadata = req.createNestedObject("metadata");
  metadata["source"] = "esp32";
  metadata["mode"] = USE_REAL_LD2410_OUT ? "ld2410_out" : "dummy_presence";
  metadata["transport"] = "wifi";

  String body;
  serializeJson(req, body);
  logLine(String("[SESSION] Start payload: ") + body);

  String response;
  int code = 0;
  bool ok = postJsonWithRetry(endpointStart(), body, response, code, 3);
  if (!ok) {
    logLine(String("[SESSION] start failed code=") + String(code));
    drawOled("Start failed", String("HTTP ") + String(code));
    return false;
  }

  String sid;
  if (!parseSessionId(response, sid)) {
    drawOled("Start parse fail");
    return false;
  }

  currentSessionId = sid;
  logLine(String("[SESSION] started sid=") + currentSessionId);
  drawOled("Session started", currentSessionId);
  return true;
}

bool sendChunk(const SensorSample& s) {
  if (currentSessionId.length() == 0) return false;

  StaticJsonDocument<1024> req;
  req["session_id"] = currentSessionId;
  req["chunk_id"] = String(DEVICE_ID) + "-" + String((unsigned long)(s.epoch_ms & 0xFFFFFFFFUL), HEX);

  JsonArray samples = req.createNestedArray("samples");
  JsonObject row = samples.createNestedObject();
  row["recorded_at"] = iso8601FromEpochMs(s.epoch_ms);
  row["mic_raw"] = s.mic_raw;
  row["mic_rms"] = s.mic_rms;
  row["mic_peak"] = s.mic_peak;
  row["temperature"] = s.temperature;
  row["humidity"] = s.humidity;
  row["breathing_rate"] = s.breathing_rate;
  row["movement_level"] = s.movement_level;
  row["presence_detected"] = s.presence_detected;

  String body;
  serializeJson(req, body);

  String response;
  int code = 0;
  bool ok = postJsonWithRetry(endpointChunk(), body, response, code, 2);
  if (!ok) {
    logLine(String("[CHUNK] send failed code=") + String(code));
    return false;
  }

  return true;
}

bool enqueuePending(const SensorSample& s) {
  if (pendingCount >= PENDING_QUEUE_CAPACITY) {
    // Drop oldest and keep newest to preserve recent continuity.
    for (uint8_t i = 1; i < pendingCount; i++) {
      pendingQueue[i - 1] = pendingQueue[i];
    }
    pendingQueue[pendingCount - 1] = s;
    logLine("[CHUNK] pending queue full, dropped oldest sample");
    return false;
  }

  pendingQueue[pendingCount] = s;
  pendingCount++;
  logLine(String("[CHUNK] queued pending count=") + String(pendingCount));
  return true;
}

bool flushOnePendingSample() {
  if (pendingCount == 0) return true;
  if (WiFi.status() != WL_CONNECTED) return false;

  if (!sendChunk(pendingQueue[0])) {
    return false;
  }

  for (uint8_t i = 1; i < pendingCount; i++) {
    pendingQueue[i - 1] = pendingQueue[i];
  }
  pendingCount--;
  logLine(String("[CHUNK] flushed one pending, left=") + String(pendingCount));
  return true;
}

void flushPendingWithBudget(uint32_t budgetMs) {
  uint32_t start = millis();
  while (pendingCount > 0 && (millis() - start) < budgetMs) {
    if (!flushOnePendingSample()) {
      delay(80);
      ensureWiFiConnected();
      continue;
    }
    delay(25);
  }
}

bool endSession() {
  if (currentSessionId.length() == 0) {
    return false;
  }

  if (stats.sample_count == 0) {
    logLine("[END] no samples captured");
    return false;
  }

  float avgAmp = (float)(stats.sum_mic_raw / stats.sample_count);
  float rmsAmp = (float)(stats.sum_mic_rms / stats.sample_count);
  float peakIntensity = stats.max_mic_peak;
  int snoreEvents = (int)stats.snore_event_count;
  float snoreScore = fminf(100.0f, avgAmp * 1.4f);
  float avgBreathing = (float)(stats.sum_breathing_rate / stats.sample_count);
  float avgTemp = (float)(stats.sum_temperature / stats.sample_count);
  float avgHum = (float)(stats.sum_humidity / stats.sample_count);

  StaticJsonDocument<1024> req;
  req["session_id"] = currentSessionId;
  req["ended_at"] = iso8601FromEpochMs(nowEpochMs());

  JsonObject summary = req.createNestedObject("summary");
  summary["sample_count"] = stats.sample_count;
  summary["average_amplitude"] = avgAmp;
  summary["rms_amplitude"] = rmsAmp;
  summary["peak_intensity"] = peakIntensity;
  summary["snore_event_count"] = snoreEvents;
  summary["snore_score"] = snoreScore;
  summary["average_breathing_rate"] = avgBreathing;
  summary["average_temperature"] = avgTemp;
  summary["average_humidity"] = avgHum;

  String body;
  serializeJson(req, body);
  logLine(String("[END] payload bytes=") + String(body.length()));

  String response;
  int code = 0;
  bool ok = postJsonWithRetry(endpointEnd(), body, response, code, 3);
  if (!ok) {
    logLine(String("[END] failed code=") + String(code));
    return false;
  }

  DynamicJsonDocument res(4096);
  if (deserializeJson(res, response) == DeserializationError::Ok) {
    const char* rec1 = res["recommendations"][0] | "Done";
    const char* patternLabel = res["breathing_pattern"]["label"] | "Breathe";
    int inhale = res["breathing_pattern"]["inhale_seconds"] | 4;
    int hold = res["breathing_pattern"]["hold_seconds"] | 0;
    int exhale = res["breathing_pattern"]["exhale_seconds"] | 6;

    latestRecommendation = String(rec1);
    latestBreathingLine = String(patternLabel) + " " + String(inhale) + "-" + String(hold) + "-" + String(exhale);

    drawOled(
      String("Ended n=") + String(stats.sample_count),
      clipText(String("Rec: ") + latestRecommendation),
      clipText(String("Breath: ") + latestBreathingLine)
    );
  } else {
    latestRecommendation = "Session complete";
    latestBreathingLine = "4-0-6 nasal";
    drawOled("Session ended", String("n=") + String(stats.sample_count), "Resp parse fallback");
  }

  return true;
}

// =========================
// Capture Logic
// =========================
void resetStats() {
  stats.sample_count = 0;
  stats.sum_mic_raw = 0.0;
  stats.sum_mic_rms = 0.0;
  stats.max_mic_peak = 0.0f;
  stats.snore_event_count = 0;
  stats.sum_breathing_rate = 0.0;
  stats.sum_temperature = 0.0;
  stats.sum_humidity = 0.0;
  pendingCount = 0;
  lastSampleMs = 0;
  logLine("[CAPTURE] Rolling stats reset");
}

bool collectSample(SensorSample& out) {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (!isnan(t)) {
    lastValidTemp = t;
  } else {
    t = lastValidTemp;
    if (millis() - lastDhtWarnMs > 6000) {
      lastDhtWarnMs = millis();
      logLine("[DHT] Temperature read failed; using last valid value");
    }
  }

  if (!isnan(h)) {
    lastValidHum = h;
  } else {
    h = lastValidHum;
    if (millis() - lastDhtWarnMs > 6000) {
      lastDhtWarnMs = millis();
      logLine("[DHT] Humidity read failed; using last valid value");
    }
  }

  float micRaw = 0.0f;
  float micRms = 0.0f;
  float micPeak = 0.0f;
  readMicMetrics(micRaw, micRms, micPeak);

  bool presence = readPresence(micRaw);
  float movement = estimateMovement(presence, micPeak);
  float breathingRate = estimateBreathingRate(presence, micRaw);

  out.epoch_ms = nowEpochMs();
  out.mic_raw = micRaw;
  out.mic_rms = micRms;
  out.mic_peak = micPeak;
  out.temperature = t;
  out.humidity = h;
  out.breathing_rate = breathingRate;
  out.movement_level = movement;
  out.presence_detected = presence;
  return true;
}

void updateStats(const SensorSample& s) {
  stats.sample_count += 1;
  stats.sum_mic_raw += s.mic_raw;
  stats.sum_mic_rms += s.mic_rms;
  if (s.mic_peak > stats.max_mic_peak) stats.max_mic_peak = s.mic_peak;
  if (s.mic_raw >= SNORE_THRESHOLD) stats.snore_event_count += 1;
  stats.sum_breathing_rate += s.breathing_rate;
  stats.sum_temperature += s.temperature;
  stats.sum_humidity += s.humidity;
}

// =========================
// Button / Status
// =========================
bool isButtonPressed() {
  const uint32_t nowMs = millis();
  bool reading = digitalRead(BUTTON_PIN);

  if (reading != buttonLastRawState) {
    buttonLastRawState = reading;
    lastDebounceMs = nowMs;
    logLine(String("[BUTTON] raw changed to ") + (reading == LOW ? "LOW" : "HIGH"));
  }

  if ((nowMs - lastDebounceMs) >= BUTTON_DEBOUNCE_MS) {
    if (reading != buttonStableState) {
      buttonStableState = reading;
      logLine(String("[BUTTON] stable changed to ") + (buttonStableState == LOW ? "LOW" : "HIGH"));
      if (buttonStableState == LOW) {
        logLine("[BUTTON] PRESS event");
        return true;
      }
    }
  }

  if ((nowMs - lastButtonPollLogMs) >= 3000) {
    lastButtonPollLogMs = nowMs;
    logLine(String("[BUTTON] poll raw=") + (reading == LOW ? "LOW" : "HIGH") +
            " stable=" + (buttonStableState == LOW ? "LOW" : "HIGH"));
  }

  return false;
}

void logHeartbeat() {
  const uint32_t nowMs = millis();
  if ((nowMs - lastHeartbeatMs) < HEARTBEAT_MS) return;
  lastHeartbeatMs = nowMs;

  logLine(
    String("[HEARTBEAT] state=") + stateName(currentState) +
    " wifi=" + (WiFi.status() == WL_CONNECTED ? "UP" : "DOWN") +
    " samples=" + String(stats.sample_count) +
    " session=" + (currentSessionId.length() ? "YES" : "NO")
  );
}

// =========================
// Setup / Loop
// =========================
void setup() {
  Serial.begin(115200);
  delay(350);

  logLine("");
  logLine("=== AGAPAI STREAMING BOOT ===");
  logLine(String("[BOOT] FW=") + FW_VERSION + " device=" + DEVICE_ID);

  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LD2410_OUT_PIN, INPUT);

  buttonLastRawState = digitalRead(BUTTON_PIN);
  buttonStableState = buttonLastRawState;
  logLine(String("[BOOT] Button initial state=") + (buttonStableState == LOW ? "LOW" : "HIGH"));

  dht.begin();
  logLine("[BOOT] DHT initialized");

  initOled();

  bool wifiOk = connectWiFiBlocking();
  if (!wifiOk) {
    logLine("[BOOT] WiFi not connected yet, retrying in loop");
  }

  syncNtpTime();
  initI2S();
  resetStats();

  drawOled("Ready", "Click1: Start", "Click2: Stop");
  logLine("[BOOT] Setup complete");
}

void loop() {
  ensureWiFiConnected();
  logHeartbeat();

  if (isButtonPressed()) {
    logLine(String("[LOOP] Button press in state=") + stateName(currentState));

    if (currentState == STATE_IDLE || currentState == STATE_ERROR) {
      if (!startSession()) {
        setState(STATE_ERROR);
        drawOled("Start failed", "Press retry");
      } else {
        resetStats();
        setState(STATE_CAPTURING);
        drawOled("Streaming...", "Click2: Stop", "T/H/BR visible");
      }
    } else if (currentState == STATE_CAPTURING) {
      setState(STATE_SUBMITTING);
    } else if (currentState == STATE_RESULT) {
      currentSessionId = "";
      latestRecommendation = "";
      latestBreathingLine = "";
      resetStats();
      setState(STATE_IDLE);
      drawOled("Ready", "Click1: Start", "Click2: Stop");
    }
  }

  if (currentState == STATE_CAPTURING) {
    if (pendingCount > 0) {
      flushOnePendingSample();
    }

    if ((millis() - lastSampleMs) >= SAMPLE_INTERVAL_MS) {
      lastSampleMs = millis();

      SensorSample s;
      if (collectSample(s)) {
        updateStats(s);

        bool sent = sendChunk(s);
        if (!sent) {
          enqueuePending(s);
        }
        logLine(String("[CHUNK] sent=") + (sent ? "1" : "0") + " count=" + String(stats.sample_count));

        drawOled(
          "Streaming...",
          String("n:") + String(stats.sample_count) + " m:" + String(s.mic_raw, 1) + " P:" + (s.presence_detected ? "1" : "0"),
          String("T:") + String(s.temperature, 1) + " H:" + String(s.humidity, 0) + " BR:" + String(s.breathing_rate, 0)
        );
      }
    }
  }

  if (currentState == STATE_SUBMITTING) {
    drawOled("Ending session...", String("n=") + String(stats.sample_count), String("pending=") + String(pendingCount));

    flushPendingWithBudget(12000);
    if (pendingCount > 0) {
      logLine(String("[END] warning unsent pending=") + String(pendingCount));
    }

    bool ok = endSession();
    if (ok) {
      setState(STATE_RESULT);
      drawOled(
        String("Done n=") + String(stats.sample_count),
        clipText(String("Rec: ") + latestRecommendation),
        clipText(String("B: ") + latestBreathingLine)
      );
      logLine("[LOOP] End success -> RESULT");
    } else {
      setState(STATE_ERROR);
      drawOled("End failed", "Press retry");
      logLine("[LOOP] End failed -> ERROR");
    }
  }

  delay(20);
}
