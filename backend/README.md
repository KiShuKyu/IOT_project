# Pala Note — PC-side development scaffold

This lets development continue while the ESP32 upload issue is unresolved.

## Features
- Flask web UI
- Manual audio file upload for testing without ESP32
- Gemini transcription + extraction of memories/tasks/appointments
- Supabase storage via REST
- Audio is processed in memory by default; it is not archived on PC

## Setup (PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```
Fill `.env` with your API credentials. Keep the Supabase service-role key private.


## Run
```powershell
python app.py
```
Then open http://127.0.0.1:5000

## Supabase schema
`schema.sql` defines the columns expected by this scaffold. Compare it with your existing schema before running; do not blindly overwrite existing tables.

