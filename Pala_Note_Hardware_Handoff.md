# Pala Note — Hardware Handoff

**Date:** 23 November 2026  
**Purpose:** Continue hardware prototyping in a fresh ChatGPT chat without losing progress.

---

## 1. Project overview

Pala Note is a voice-enabled IoT memory/project assistant. The hardware prototype is intended to capture voice, send it to the existing Pala Note backend over Wi-Fi, receive a response, and play spoken output. An OLED will show basic status.

The software MVP is already working on the PC/backend side. This handoff covers the hardware work only.

## 2. Hardware inventory (user-confirmed)

- ESP32 development board, 30 pins
- OLED screen (exact model/interface not yet identified)
- Speaker (magnet speaker; impedance and wattage not yet identified)
- Cylindrical 2-pin microphone (type/specs not identified; not selected for primary digital capture path yet)
- Charging module (exact model not yet identified)
- 2000 mAh, 3.7 V lithium battery
- Battery holder
- Breadboard
- INMP441 I2S digital MEMS microphone module
- MAX98357A I2S audio amplifier module
- MT3608 boost converter module

Do not assume the modules' exact versions, pinouts, or ratings until photos/markings are checked.

## 3. ESP32 board identification

From user-provided photos:
- Board is a 30-pin ESP32 DevKit-style board.
- The module appears to be in the ESP32-WROOM-32 / classic ESP32 family (photo marking is consistent with ESP-32; verify module marking if needed).
- USB connector: Micro-USB.
- Board labels visible include: VIN, GND, D13, D12, D14, D27, D26, D25, D33, D32, D35, D34, VN, VP, EN on one side; and 3V3, GND, D15, D2, D4, RX2, TX2, D5, D18, D19, D21, RX0, TX0, D22, D23 on the other.
- User's board is connected to the PC on COM5.

## 4. Verified ESP32 test

The user successfully uploaded and ran the following Arduino sketch:

```cpp
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("PALA NOTE ESP32 ONLINE");
}

void loop() {
  Serial.println("ESP32 is running...");
  delay(2000);
}
```

Serial Monitor at 115200 showed:

```text
PALA NOTE ESP32 ONLINE
ESP32 is running...
ESP32 is running...
ESP32 is running...
```

**Status: PASS.** Board is detected, code upload works, and serial output is verified.

Arduino IDE settings used/recommended:
- Board: ESP32 Dev Module
- Port: COM5
- Upload speed: 115200
- Serial Monitor baud: 115200

If upload gets stuck at `Connecting...`, try holding BOOT during upload and release when upload begins.

## 5. Intended architecture

Voice input path:

**INMP441 → ESP32 I2S capture → Wi-Fi → Pala Note backend → response**

Voice output path:
**Backend response/audio → ESP32 → I2S → MAX98357A → speaker**

OLED:
- Boot status
- Wi-Fi status
- Listening / processing / response status
- Basic prompts or short response text (depending on display size and interface)

Power architecture is not yet decided or wired. Battery/charger/boost must be designed and tested separately.

## 6. Planned staged build (test each stage before adding the next)

### Stage 1 — ESP32 basic setup (COMPLETED)
- USB connection
- Arduino IDE board/port configuration
- Test serial output

### Stage 2 — INMP441 microphone
- Identify exact INMP441 breakout pin labels from a clear photo.
- Choose ESP32 GPIOs for I2S clock, word select, and data based on the actual board and avoid boot-strapping/conflicting pins.
- Connect on breadboard with exact pin-by-pin guidance.
- Upload I2S capture test and verify that microphone data is being read.

### Stage 3 — OLED
- Identify exact OLED model and pin labels; determine I2C vs SPI and operating voltage.
- Wire and run display test.
- Display simple status messages.

### Stage 4 — MAX98357A and speaker
- Identify amplifier module pin labels and speaker impedance/power rating.
- Wire I2S audio output and speaker correctly.
- Run a controlled audio playback test.

### Stage 5 — Wi-Fi and backend integration
- Connect ESP32 to Wi-Fi.
- Implement safe communication with the existing Pala Note backend.
- Do not place Gemini/Supabase/backend secrets in ESP32 firmware.
- Add device authentication before allowing hardware/network access to protected backend endpoints.

### Stage 6 — Battery, charging, and power
- Identify exact charging board (including whether protection circuitry is present).
- Confirm battery chemistry, connector polarity, and holder wiring.
- Check MT3608 input/output and set output voltage with a multimeter before connecting electronics.
- Decide whether boost converter is actually needed; do not use it by default.
- Plan power rails and common ground, and validate separately before powering the full system.
- Never charge or use a lithium battery with unidentified polarity, damaged wiring, or an unsuitable charging module.

### Stage 7 — Integrated prototype
- Integrate tested modules incrementally.
- Confirm microphone capture, backend round trip, and speaker response independently.
- Finalize wiring and enclosure only after stable bench tests.

## 7. Safety and wiring rules

- **Do not wire the battery, charger, or MT3608 yet.** The power circuit is unverified.
- ESP32 GPIO logic is 3.3 V; do not apply 5 V logic signals to GPIO.
- Do not connect amplifier speaker outputs to ESP32 GPIO or ground.
- Do not assume speaker impedance/wattage; inspect markings or measure/confirm specifications.
- Do not assume OLED pinout or voltage without identifying the module.
- Use breadboard wiring for early prototyping; keep power disconnected while changing wiring.
- For every assembly step, provide exact pin-to-pin connections, breadboard placement, suggested wire colors, and a test sketch before moving to the next stage.
- Keep tests isolated: add one component at a time, test, then proceed.

## 8. Immediate next task

**Start Stage 2: INMP441 microphone wiring and test.**

Ask the user for a clear close-up photo of the INMP441 module by itself, with all pin labels visible. Once the module pin labels are confirmed, provide:
1. Exact INMP441-to-ESP32 pin map using the user's 30-pin board labels.
2. Breadboard placement instructions, including rows/rails.
3. Wire color suggestions.
4. Explicit warnings about any pins to avoid.
5. A minimal Arduino I2S microphone test sketch.
6. A simple test procedure and expected output.

Do not begin wiring until the INMP441 pin labels are verified.

## 9. Known unknowns to resolve

- INMP441 breakout pin labels and exact board version
- OLED model, pin labels, interface, voltage
- MAX98357A breakout pin labels/version
- Speaker impedance and power rating
- Cylindrical microphone specifications/type and whether it is an analog electret mic (not yet characterized)
- Charging module model and protection features
- Battery connector/polarity and holder type
- Whether MT3608 is needed in final power design
- Final battery power strategy and safe switching/charging arrangement

## 10. Workflow preferences for the next chat

- Be precise and procedural.
- Build and test one stage at a time, but avoid unnecessary slow inspection cycles.
- Give exact breadboard connections, not generic descriptions.
- Do not assume parts are already wired or that their exact models are known.
- Wait for the user's test result before proceeding to the next stage.
- Hardware focus: move toward a functional prototype efficiently while prioritizing safe power design.

---

## Current progress snapshot

| Item | Status |
|---|---|
| ESP32 board identified broadly | Done (30-pin classic ESP32 DevKit-style / WROOM family likely) |
| USB/COM5 detection | Passed |
| Arduino upload | Passed |
| Serial test | Passed |
| Breadboard available | Confirmed |
| Components inventory | Confirmed (list above) |
| INMP441 wiring | Not started |
| OLED wiring | Not started / model unknown |
| MAX98357A wiring | Not started |
| Battery/charger/boost wiring | Not started — intentionally held pending verification |
| Backend integration from ESP32 | Not started |

