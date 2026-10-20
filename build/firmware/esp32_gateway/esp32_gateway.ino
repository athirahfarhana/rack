/*
 * ESP32 Rack Gateway firmware - real replacement for simulate_gateway.py.
 *
 * Implements the exact protocol the backend expects (see
 * backend/app/mqtt_client.py docstring):
 *
 *   Publish (this device -> backend):
 *     {prefix}/{GATEWAY_ID}/tx/heartbeat   every HEARTBEAT_INTERVAL_MS
 *     {prefix}/{GATEWAY_ID}/tx/discovery   once, on first MQTT connect
 *     {prefix}/{GATEWAY_ID}/tx/button      on each Green/Red button press
 *
 *   Subscribe (backend -> this device):
 *     {prefix}/{GATEWAY_ID}/rx/led         turns the status LED on/off
 *
 * Wiring (Arduino Nano ESP32 pin labels - matches the board's silkscreen):
 *   Green "OK" button  -> D2, other leg to GND (uses internal pull-up)
 *   Red "Cancel" button -> D3, other leg to GND (uses internal pull-up)
 *   Status LED          -> D4, through a resistor to GND
 *
 * Required libraries (Arduino IDE -> Tools -> Manage Libraries):
 *   - PubSubClient (by Nick O'Leary)
 *   - ArduinoJson  (by Benoit Blanchon, v6.x)
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ---------------------------------------------------------------- settings
const char *WIFI_SSID = "UST_INFINITY_LAB";
const char *WIFI_PASSWORD = "infilabs@u5t";

const char *MQTT_HOST = "broker.hivemq.com"; // match backend/.env MQTT_HOST
const int MQTT_PORT = 1883;
const char *TOPIC_PREFIX = "warehouse/racks"; // match backend/.env MQTT_TOPIC_PREFIX

// Pick a unique ID for this rack's gateway - this is what you'll drag onto
// a zone in the Admin Dashboard's Mapping screen.
const char *GATEWAY_ID = "GW-ESP32-01";

const int PIN_BUTTON_GREEN = D2;
const int PIN_BUTTON_RED = D3;
const int PIN_LED = D4;

const unsigned long HEARTBEAT_INTERVAL_MS = 60000; // matches HEARTBEAT_INTERVAL_SEC=60
const unsigned long DEBOUNCE_MS = 250;

// ------------------------------------------------------------------ state
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

String nodeUuid;      // this device's own MAC - doubles as its one zone module's id
String topicHeartbeat, topicDiscovery, topicButton, topicLedRx;

unsigned long lastHeartbeatAt = 0;
unsigned long bootMillis = 0;
unsigned long lastGreenPressAt = 0;
unsigned long lastRedPressAt = 0;
int lastGreenState = HIGH;
int lastRedState = HIGH;

// --------------------------------------------------------------- wifi/mqtt
void connectWiFi() {
  Serial.printf("Connecting to WiFi '%s'...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.printf("\nWiFi connected. IP=%s MAC=%s\n", WiFi.localIP().toString().c_str(), WiFi.macAddress().c_str());
}

void publishDiscovery() {
  StaticJsonDocument<256> doc;
  doc["event"] = "node_discovered";
  doc["gateway_id"] = GATEWAY_ID;
  doc["node_uuid"] = nodeUuid;
  doc["hardware_rev"] = "1.0";
  JsonArray caps = doc.createNestedArray("capabilities");
  caps.add("led_rgb");

  char buf[256];
  size_t n = serializeJson(doc, buf);
  mqtt.publish(topicDiscovery.c_str(), (uint8_t *)buf, n);
  Serial.printf("Published discovery for node %s\n", nodeUuid.c_str());
}

void publishHeartbeat() {
  StaticJsonDocument<256> doc;
  doc["event"] = "heartbeat";
  doc["gateway_id"] = GATEWAY_ID;
  doc["status"] = "online";
  doc["active_nodes_count"] = 1;
  doc["wifi_rssi"] = WiFi.RSSI();
  doc["uptime_seconds"] = (millis() - bootMillis) / 1000;

  char buf[256];
  size_t n = serializeJson(doc, buf);
  mqtt.publish(topicHeartbeat.c_str(), (uint8_t *)buf, n);
  Serial.println("Heartbeat sent");
}

void publishButtonPress(const char *button) {
  StaticJsonDocument<192> doc;
  doc["event"] = "button_press";
  doc["gateway_id"] = GATEWAY_ID;
  doc["node_uuid"] = nodeUuid;
  doc["button"] = button;

  char buf[192];
  size_t n = serializeJson(doc, buf);
  mqtt.publish(topicButton.c_str(), (uint8_t *)buf, n);
  Serial.printf("Button press sent: %s\n", button);
}

// rx/led handler - backend tells us to turn the rack's indicator LED on/off.
void onMqttMessage(char *topic, byte *payload, unsigned int length) {
  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) {
    Serial.printf("Bad LED payload: %s\n", err.c_str());
    return;
  }

  const char *state = doc["state"] | "OFF";
  bool on = strcmp(state, "ON") == 0;
  digitalWrite(PIN_LED, on ? HIGH : LOW);
  Serial.printf("LED set to %s (color=%s)\n", state, (const char *)(doc["color_hex"] | "-"));
}

void connectMQTT() {
  while (!mqtt.connected()) {
    Serial.print("Connecting to MQTT broker...");
    String clientId = "esp32-" + nodeUuid;
    if (mqtt.connect(clientId.c_str())) {
      Serial.println(" connected.");
      mqtt.subscribe(topicLedRx.c_str());
      publishDiscovery();
    } else {
      Serial.printf(" failed, rc=%d. Retrying in 2s...\n", mqtt.state());
      delay(2000);
    }
  }
}

// ------------------------------------------------------------- buttons
void checkButtons() {
  int green = digitalRead(PIN_BUTTON_GREEN);
  if (green == LOW && lastGreenState == HIGH && millis() - lastGreenPressAt > DEBOUNCE_MS) {
    publishButtonPress("OK_GREEN");
    lastGreenPressAt = millis();
  }
  lastGreenState = green;

  int red = digitalRead(PIN_BUTTON_RED);
  if (red == LOW && lastRedState == HIGH && millis() - lastRedPressAt > DEBOUNCE_MS) {
    publishButtonPress("CANCEL_RED");
    lastRedPressAt = millis();
  }
  lastRedState = red;
}

// ------------------------------------------------------------------ setup
void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUTTON_GREEN, INPUT_PULLUP);
  pinMode(PIN_BUTTON_RED, INPUT_PULLUP);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LOW);

  bootMillis = millis();
  connectWiFi();
  nodeUuid = WiFi.macAddress();

  topicHeartbeat = String(TOPIC_PREFIX) + "/" + GATEWAY_ID + "/tx/heartbeat";
  topicDiscovery = String(TOPIC_PREFIX) + "/" + GATEWAY_ID + "/tx/discovery";
  topicButton = String(TOPIC_PREFIX) + "/" + GATEWAY_ID + "/tx/button";
  topicLedRx = String(TOPIC_PREFIX) + "/" + GATEWAY_ID + "/rx/led";

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
  connectMQTT();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }
  if (!mqtt.connected()) {
    connectMQTT();
  }
  mqtt.loop(); // must be called often - keeps connection alive + delivers rx/led promptly

  checkButtons();

  if (millis() - lastHeartbeatAt >= HEARTBEAT_INTERVAL_MS) {
    publishHeartbeat();
    lastHeartbeatAt = millis();
  }
}
