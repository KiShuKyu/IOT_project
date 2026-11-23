"""Gemini helpers for the Pala Note MVP.

Audio is sent to Gemini for processing and is not written to disk by this app.
"""

import json
import os
import re
from datetime import datetime
from functools import lru_cache

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()


@lru_cache(maxsize=1)
def get_client():
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to the Python .env file.")
    return genai.Client(api_key=GEMINI_API_KEY)


def _extract_json(text: str) -> dict:
    """Parse a JSON response, tolerating accidental Markdown fences."""
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text or "", flags=re.I)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError(f"Gemini did not return JSON. Reply was: {cleaned[:300]}")
        return json.loads(cleaned[start : end + 1])


def analyze_audio(wav_bytes: bytes, local_now: str) -> dict:
    """Transcribe audio and classify the recording into notes/tasks/appointments."""
    prompt = f"""
You are the speech-to-text and personal-memory organiser for Pala Note.
The attached audio is a short personal voice note. It may contain English,
Hindi, or a mixture. Transcribe what was actually said; do not invent words.

Current local date and time (Asia/Kolkata): {local_now}

Return ONLY a JSON object with this exact shape:
{{
  "transcript": "full transcript",
  "items": [
    {{
      "type": "task" | "appointment" | "memory",
      "title": "short title, no more than 10 words",
      "summary": "one concise sentence preserving the important detail",
      "due": "YYYY-MM-DDTHH:MM or null",
      "start": "YYYY-MM-DDTHH:MM or null",
      "tags": ["short-tag"]
    }}
  ]
}}

Rules:
- A task is an action the speaker explicitly intends or needs to do.
- An appointment is an event/meeting with a date or time.
- A memory is an idea, fact, preference, or information to retain.
- Split a recording into multiple items only when it contains distinct points.
- Resolve relative dates such as tomorrow/next Monday using the local date above.
- Use due only for tasks and start only for appointments.
- Do not invent a due date or appointment time if none was stated.
- If there is no intelligible speech, set transcript to an empty string and items to [].
""".strip()

    response = get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )

    payload = _extract_json(response.text or "")
    transcript = str(payload.get("transcript") or "").strip()
    cleaned_items = []

    for raw in (payload.get("items") or [])[:8]:
        if not isinstance(raw, dict):
            continue
        item_type = str(raw.get("type") or "memory").lower().strip()
        if item_type not in {"task", "appointment", "memory"}:
            item_type = "memory"
        title = str(raw.get("title") or transcript[:70] or "Voice note").strip()[:160]
        summary = str(raw.get("summary") or transcript).strip()[:1000]
        due = raw.get("due") if item_type == "task" else None
        start = raw.get("start") if item_type == "appointment" else None
        tags = raw.get("tags") if isinstance(raw.get("tags"), list) else []
        cleaned_items.append({
            "type": item_type,
            "title": title,
            "summary": summary,
            "due": str(due)[:32] if due else None,
            "start": str(start)[:32] if start else None,
            "tags": [str(tag)[:40] for tag in tags[:8]],
        })

    if transcript and not cleaned_items:
        cleaned_items.append({
            "type": "memory",
            "title": transcript[:70],
            "summary": transcript,
            "due": None,
            "start": None,
            "tags": [],
        })

    return {"transcript": transcript, "items": cleaned_items}


def answer_question(question: str, memory_context: str, local_now: str) -> str:
    """Answer a question using only the user's stored Pala Note memories."""
    prompt = f"""
You are Pala Note, a personal memory assistant.
Current local date and time (Asia/Kolkata): {local_now}

Answer the user's question using the stored notes below. Do not pretend to
remember anything that is not in the notes. If the information is missing,
say that it is not present in the saved notes. Be concise and specific.

SAVED NOTES:
{memory_context or '(No notes have been saved yet.)'}

USER QUESTION:
{question}
""".strip()

    response = get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2),
    )
    answer = (response.text or "").strip()
    return answer or "I could not generate an answer from the saved notes."
