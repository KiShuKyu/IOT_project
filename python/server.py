"""Pala Note local Python server.

Run on the same Wi-Fi network as the ESP32:
    python -m pip install -r requirements.txt
    copy .env.example to .env and edit it
    python server.py
Then open http://localhost:5000.
"""

import hashlib
import hmac
import io
import os
import socket
import threading
import wave
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request

import ai
import storage

load_dotenv()

TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Asia/Kolkata"))
DEVICE_TOKEN = os.getenv("DEVICE_TOKEN", "").strip()
ESP32_BASE_URL = os.getenv("ESP32_BASE_URL", "").strip().rstrip("/")
MAX_AUDIO_BYTES = 1_500_000

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_AUDIO_BYTES

NOTE_PROCESSING = threading.Event()


def now_local():
    return datetime.now(TIMEZONE)


def now_iso():
    return now_local().isoformat(timespec="seconds")


def token_is_valid(value: str) -> bool:
    return bool(DEVICE_TOKEN) and hmac.compare_digest(value or "", DEVICE_TOKEN)


def require_device_token():
    if not token_is_valid(request.headers.get("X-Token", "")):
        abort(401, description="Invalid device token")


def device_request(method: str, endpoint: str):
    if not ESP32_BASE_URL:
        return None, (jsonify(ok=False, error="Set ESP32_BASE_URL in .env first."), 503)
    url = f"{ESP32_BASE_URL}{endpoint}"
    try:
        response = requests.request(
            method,
            url,
            headers={"X-Token": DEVICE_TOKEN},
            timeout=(3, 8),
        )
        try:
            body = response.json()
        except ValueError:
            body = {"message": response.text[:300]}
        if not response.ok:
            return None, (jsonify(ok=False, device_status=response.status_code, error=body), response.status_code)
        return body, None
    except requests.RequestException as exc:
        return None, (jsonify(ok=False, error=f"Cannot reach ESP32 at {url}: {exc}"), 502)


def validate_wav(audio_bytes: bytes):
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frame_count = wav.getnframes()
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"Invalid WAV file: {exc}") from exc

    if channels != 1 or sample_width != 2 or sample_rate != 16000:
        raise ValueError(
            f"Expected 16 kHz mono 16-bit PCM; received channels={channels}, "
            f"sample_width={sample_width}, sample_rate={sample_rate}."
        )
    if frame_count < 8000:
        raise ValueError("Recording is shorter than 0.5 seconds.")


@app.get("/")
def index():
    return render_template("index.html")


# Browser -> Flask -> ESP32 control
@app.post("/api/device/start")
def api_device_start():
    body, error = device_request("POST", "/api/record/start")
    if error:
        return error
    return jsonify(body)


@app.post("/api/device/stop")
def api_device_stop():
    body, error = device_request("POST", "/api/record/stop")
    if error:
        return error
    return jsonify(body)


@app.post("/api/device/retry-upload")
def api_device_retry_upload():
    body, error = device_request("POST", "/api/record/upload")
    if error:
        return error
    return jsonify(body)


@app.get("/api/device/status")
def api_device_status():
    # While Gemini is processing an uploaded note, the ESP32 is waiting for
    # the HTTP response and cannot serve its own status endpoint.
    if NOTE_PROCESSING.is_set():
        return jsonify(ok=True, recording=False, mic_ready=False,
                       upload_pending=True, processing_note=True,
                       samples=0, duration_ms=0, max_seconds=20, ip="ESP32 uploading")
    body, error = device_request("GET", "/api/status")
    if error:
        return error
    return jsonify(body)


# ESP32 -> Flask -> Gemini -> Supabase
@app.post("/api/note")
def api_receive_note():
    require_device_token()
    audio_bytes = request.get_data(cache=False)
    if not audio_bytes:
        return jsonify(ok=False, error="No audio bytes received."), 400

    audio_hash = hashlib.sha256(audio_bytes).hexdigest()
    existing = storage.get_recording(audio_hash)
    if existing:
        return jsonify(ok=True, duplicate=True, transcript=existing["transcript"], items=existing["items"])

    NOTE_PROCESSING.set()
    try:
        try:
            validate_wav(audio_bytes)
            analysis = ai.analyze_audio(audio_bytes, now_local().strftime("%A, %d %B %Y %I:%M %p"))
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        except Exception as exc:
            # A non-200 response tells the ESP32 to retain its LittleFS file.
            print(f"[Gemini] Processing failed: {exc}")
            return jsonify(ok=False, error=f"Gemini processing failed: {exc}"), 503

        transcript = analysis["transcript"]
        items = analysis["items"]
        if not transcript:
            return jsonify(ok=False, error="No intelligible speech detected."), 422
        if not items:
            items = [{
                "type": "memory",
                "title": transcript[:70],
                "summary": transcript,
                "due": None,
                "start": None,
                "tags": [],
            }]

        created_at = now_iso()
        saved = storage.save_recording(audio_hash, transcript, items, created_at)
        stored_items = saved["recording"]["items"]
        print(f"[NOTE] Saved {len(stored_items)} item(s). Transcript: {transcript}")
        # Audio is not written to disk. Once this response is 200, the ESP32 deletes
        # its temporary LittleFS recording.
        return jsonify(
            ok=True,
            duplicate=saved["duplicate"],
            transcript=transcript,
            items=stored_items,
        )
    finally:
        NOTE_PROCESSING.clear()


@app.get("/api/items")
def api_items():
    return jsonify(items=storage.recent_items(40))


@app.post("/api/ask")
def api_ask():
    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question") or "").strip()
    if not question:
        return jsonify(ok=False, error="Enter a question first."), 400
    if len(question) > 1000:
        return jsonify(ok=False, error="Question is too long (maximum 1000 characters)."), 400

    try:
        answer = ai.answer_question(
            question,
            storage.memory_context(50),
            now_local().strftime("%A, %d %B %Y %I:%M %p"),
        )
    except Exception as exc:
        print(f"[Gemini] Question failed: {exc}")
        return jsonify(ok=False, error=f"Gemini request failed: {exc}"), 503

    storage.add_question(question, answer, now_iso())
    return jsonify(ok=True, answer=answer)


def lan_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


if __name__ == "__main__":
    if not DEVICE_TOKEN or DEVICE_TOKEN in {"change-me", "replace-this-with-a-long-random-token"}:
        raise SystemExit("Set a strong DEVICE_TOKEN in .env before starting the server.")
    try:
        storage.check_connection()
    except Exception as exc:
        raise SystemExit(f"Supabase connection/schema check failed: {exc}")
    pc_ip = lan_ip()
    print("\n========== PALA NOTE MVP ==========")
    print("Web page:      http://localhost:5000")
    print(f"LAN web page:  http://{pc_ip}:5000")
    print(f"ESP32 target:  {ESP32_BASE_URL or 'NOT CONFIGURED - set ESP32_BASE_URL in .env'}")
    print("Audio storage: temporary on ESP32 LittleFS; no WAV archive on the PC")
    print("===================================\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
