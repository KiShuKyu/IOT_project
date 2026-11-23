# Pala Note MVP

This is the first working software milestone for the Pala Note build:

1. A browser page sends START/STOP to a Python Flask server.
2. Flask forwards those commands to the ESP32.
3. The ESP32 reads the INMP441 in small chunks and writes a WAV file to LittleFS.
4. On STOP, the ESP32 uploads the WAV to Flask.
5. Flask sends the audio to Gemini for transcription and note classification.
6. Supabase stores the transcript and extracted text metadata (task, appointment, memory, dates, tags).
7. The browser can ask text questions using the saved Supabase memories.

The Python server does not archive WAV files. The ESP32 retains one temporary LittleFS recording until the server confirms that processing and storage succeeded. Speaker playback and OLED status are deliberately deferred until the recording-to-Supabase path is stable.

## Hardware pin map used by this firmware

This is the wiring from the previously tested microphone setup, not the alternative pin map shown in the uploaded Wokwi diagram.

| Part | Pin | ESP32 |
|---|---|---:|
| INMP441 | VDD | 3V3 |
| INMP441 | GND | GND |
| INMP441 | L/R | GND |
| INMP441 | SCK | GPIO 26 |
| INMP441 | WS | GPIO 25 |
| INMP441 | SD | GPIO 33 |
| OLED | SDA | GPIO 21 |
| OLED | SCL | GPIO 22 |
| MAX98357A | BCLK | GPIO 26 (shared clock) |
| MAX98357A | LRC | GPIO 25 (shared clock) |
| MAX98357A | DIN | GPIO 32 |

This firmware milestone uses the microphone only. It does not initialize the MAX98357A or OLED; leave the existing wiring in place.

## 1. Create the Supabase database

1. Create/open your Supabase project.
2. Open **SQL Editor** in the Supabase Dashboard.
3. Open `supabase/schema.sql` from this project, copy the entire file, paste it into SQL Editor, and run it once.
4. Open the project **Connect** panel / API Keys page and copy the Project URL and a server-side Secret key. The older `service_role` key is also accepted by this code.

The SQL creates `recordings`, `items`, and `questions`. Row Level Security is enabled. Do not create public/anon policies for these tables. In the Supabase Data API settings, make sure the `public` schema and the `save_note_recording` function are exposed to the Data API. The Python backend uses the server-side secret key; never put that key in the HTML, JavaScript, ESP32 firmware, or a public Git repository.

## 2. Configure the Python server

Use Python 3.12 for this first build. The current Supabase Python client supports Python 3.12 and newer.

Open PowerShell in the `python` folder:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `python/.env` and set:

- `GEMINI_API_KEY`: your key from Google AI Studio.
- `GEMINI_MODEL`: leave as `gemini-3.8-flash` initially.
- `SUPABASE_URL`: the Project URL from Supabase.
- `SUPABASE_SECRET_KEY`: the server-side Secret key from Supabase. Do not use a publishable key here.
- `ESP32_BASE_URL`: fill this after the ESP32 prints its IP address in Serial Monitor.
- `DEVICE_TOKEN`: replace the example text with a long random string. Copy the exact same string into the ESP32 sketch.

Do not upload `.env` to GitHub.

## 3. Find the computer's Wi-Fi IP address

In PowerShell, run:

```powershell
ipconfig
```

Under the active Wi-Fi adapter, copy the `IPv4 Address`, for example `192.168.1.10`.

Open `esp32/PalaNoteMVP/PalaNoteMVP.ino` and edit these values near the top:

```cpp
const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* PYTHON_NOTE_URL = "http://192.168.1.10:5000/api/note";
const char* DEVICE_TOKEN = "the-same-long-token-as-python-dot-env";
```

Replace `192.168.1.10` with your computer's actual Wi-Fi IPv4 address. Keep the ESP32 and computer on the same Wi-Fi network.

## 4. Upload the ESP32 firmware

In Arduino IDE:

1. Open `esp32/PalaNoteMVP/PalaNoteMVP.ino`.
2. Select board **ESP32 Dev Module**.
3. Select the correct COM port.
4. In **Tools → Partition Scheme**, select **No OTA (2MB APP / 2MB SPIFFS)** or another partition option that has a SPIFFS data partition large enough for a temporary WAV.
5. Select 115200 baud in Serial Monitor.
6. Upload the sketch and open Serial Monitor.

Expected serial output includes:

```text
[FS] LittleFS ready: ...
[WiFi] Connected. ESP32 IP: 192.168.x.x
[HTTP] ESP32 control API started on port 80
[READY] Open the Python web page on your computer.
```

Copy the ESP32 IP shown in Serial Monitor. If the ESP32 does not connect to Wi-Fi, verify the SSID/password and use a 2.4 GHz Wi-Fi network.

## 5. Set the ESP32 IP in Python

Open `python/.env` and set (use the IP actually printed by the ESP32):

```env
ESP32_BASE_URL=http://192.168.x.x
```

Do not add `/api/status` or a port; the server adds the endpoint itself.

## 6. Start the Python server

In the same PowerShell window, from `python`:

```powershell
.venv\Scripts\Activate.ps1
python server.py
```

On startup, the server checks the Supabase connection and prints its local web address. Open:

```text
http://localhost:5000
```

The Python computer and ESP32 must be on the same LAN. If the page cannot reach the ESP32, allow Python through Windows Defender Firewall on **Private networks** and verify both IP addresses are on the same subnet.

## 7. First recording test

1. Confirm the page says `ESP32 connected`.
2. Click **Start recording**.
3. Speak for 3–5 seconds in a normal voice.
4. Click **Stop recording**.
5. Wait for the upload and Gemini processing to finish.
6. Confirm the transcript and extracted note appear under **Saved notes**.
7. Ask a question such as: `What did I just ask myself to remember?`

A recording is limited to 20 seconds in this first version. The ESP32 keeps one pending WAV in LittleFS until Flask returns HTTP 200. If upload or AI processing fails, the file remains on the ESP32 and the page enables **Retry upload**. Once processing and Supabase storage succeed, the ESP32 deletes its temporary WAV.

## Why this avoids the previous linker error

Do not use the previous global array `int16_t audioBuffer[16000 * 5]`. It reserves 160,000 bytes of internal DRAM before Wi-Fi, I2S, and other libraries are counted. This firmware keeps only a small I2S conversion buffer in RAM and writes the recording incrementally to LittleFS.

## Troubleshooting

- **LittleFS mount failed:** select a partition scheme with a SPIFFS data partition, then upload again. On the first run, the sketch may format the LittleFS data partition if it is not already formatted; this clears files in that filesystem partition.
- **Supabase connection/schema check failed:** check the Project URL, server-side key, and that `supabase/schema.sql` ran successfully.
- **ESP32 not reachable:** confirm `ESP32_BASE_URL`, same Wi-Fi network, and Windows firewall permissions.
- **Upload pending:** confirm Flask is running, `PYTHON_NOTE_URL` points to the computer's correct IPv4 address, and the token matches in both files.
- **401 unauthorized:** compare `DEVICE_TOKEN` character-for-character in the sketch and `.env`.
- **Gemini processing failed:** verify `GEMINI_API_KEY`, available API quota, and the error shown in the Python terminal. The ESP32 retains the WAV for retry.
- **Poor transcript quality:** do not change wiring yet. First check captured audio with actual voice notes; the current sample conversion is an initial calibration, not a guaranteed final audio tuning.

## Privacy and scope

The Python server holds each incoming WAV in memory only long enough to send it to Gemini. It does not save audio files. Supabase stores text transcripts, summaries, tags, task/appointment fields, and timestamps. The ESP32 temporarily uses LittleFS as a retry buffer until the server confirms successful processing.

This is a local-network development server. Do not expose Flask or the ESP32 API directly to the public internet.
