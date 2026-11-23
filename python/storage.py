"""Supabase storage for transcripts and structured Pala Note memories.

Only the Python server imports the Supabase server-side key. Never expose this
key to the browser or put it in the ESP32 firmware.
"""

import os
from functools import lru_cache

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = (
    os.getenv("SUPABASE_SECRET_KEY", "").strip()
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
)


@lru_cache(maxsize=1)
def get_client():
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL is missing in python/.env")
    if not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_SECRET_KEY is missing in python/.env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def check_connection():
    # A zero-row SELECT still confirms the table and API credentials are valid.
    get_client().table("items").select("id").limit(1).execute()


def get_recording(audio_hash: str):
    client = get_client()
    recording_response = (
        client.table("recordings")
        .select("audio_hash, transcript, created_at")
        .eq("audio_hash", audio_hash)
        .limit(1)
        .execute()
    )
    if not recording_response.data:
        return None

    items_response = (
        client.table("items")
        .select("id, item_type, title, summary, due, start, tags, created_at")
        .eq("recording_hash", audio_hash)
        .order("id", desc=False)
        .execute()
    )
    items = []
    for row in items_response.data or []:
        item = dict(row)
        item["type"] = item.pop("item_type", "memory")
        item["tags"] = item.get("tags") or []
        items.append(item)

    recording = recording_response.data[0]
    return {
        "audio_hash": recording["audio_hash"],
        "transcript": recording["transcript"],
        "created_at": recording["created_at"],
        "items": items,
    }


def save_recording(audio_hash: str, transcript: str, items: list, created_at: str):
    """Atomically store a recording through the SQL RPC; duplicate-safe on retry."""
    existing = get_recording(audio_hash)
    if existing:
        return {"duplicate": True, "recording": existing}

    payload = {
        "p_audio_hash": audio_hash,
        "p_transcript": transcript,
        "p_created_at": created_at,
        "p_items": items,
    }
    result = get_client().rpc("save_note_recording", payload).execute()
    rpc_data = result.data
    if isinstance(rpc_data, list) and rpc_data:
        rpc_data = rpc_data[0]
    duplicate = bool(rpc_data.get("duplicate")) if isinstance(rpc_data, dict) else False
    recording = get_recording(audio_hash)
    if not recording:
        raise RuntimeError("Supabase RPC returned but the recording could not be read back.")
    return {"duplicate": duplicate, "recording": recording}


def recent_items(limit: int = 40):
    response = (
        get_client().table("items")
        .select("id, item_type, title, summary, transcript, due, start, tags, created_at")
        .order("created_at", desc=True)
        .order("id", desc=True)
        .limit(int(limit))
        .execute()
    )
    result = []
    for row in response.data or []:
        item = dict(row)
        item["type"] = item.pop("item_type", "memory")
        item["tags"] = item.get("tags") or []
        result.append(item)
    return result


def memory_context(limit: int = 50):
    items = recent_items(limit)
    lines = []
    for item in reversed(items):
        parts = [f"[{item['type'].upper()}] {item['title']}"]
        if item.get("summary"):
            parts.append(item["summary"])
        if item.get("due"):
            parts.append(f"Due: {item['due']}")
        if item.get("start"):
            parts.append(f"When: {item['start']}")
        if item.get("transcript"):
            parts.append(f"Original transcript: {item['transcript']}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)[:14000]


def add_question(question: str, answer: str, created_at: str):
    get_client().table("questions").insert({
        "question": question,
        "answer": answer,
        "created_at": created_at,
    }).execute()
