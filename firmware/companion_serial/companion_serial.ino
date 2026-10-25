// ESP32 development responder. Install ArduinoJson 7 through Library Manager.
// This verifies the companion connection; it does not run AI or execute tasks.
#include <ArduinoJson.h>

String pending;

void setup() {
  Serial.begin(115200);
  pending.reserve(512);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      JsonDocument incoming;
      if (!deserializeJson(incoming, pending) && incoming["protocol"].as<int>() == 1) {
        const char* type = incoming["type"] | "";
        if (!strcmp(type, "hello") || !strcmp(type, "ping")) {
          JsonDocument reply;
          reply["type"] = !strcmp(type, "hello") ? "hello_ack" : "pong";
          reply["device"] = "device-companion";
          reply["protocol"] = 1;
          reply["nonce"] = incoming["nonce"];
          serializeJson(reply, Serial);
          Serial.println();
        }
      }
      pending = "";
    } else if (pending.length() < 512) {
      pending += c;
    } else {
      pending = "";
    }
  }
}
