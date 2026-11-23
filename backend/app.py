from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename
import mimetypes
from config import Config
from gemini_service import GeminiService
from supabase_service import SupabaseService
import hashlib
from datetime import datetime, timezone
import json
from google import genai
import requests
import base64
from io import BytesIO
from flask import send_file
from openhands_service import OpenHandsService, OpenHandsServiceError
from pathlib import Path

app=Flask(__name__)
app.config['MAX_CONTENT_LENGTH']=Config.MAX_UPLOAD_MB*1024*1024
supabase=SupabaseService(Config.SUPABASE_URL,Config.SUPABASE_KEY,Config.ITEMS_TABLE)

# def device_auth_ok():
#     # If token is configured, require it. For local manual upload, token is not required.
#     if not Config.DEVICE_TOKEN: return True
#     return request.headers.get('X-Device-Token','') == Config.DEVICE_TOKEN
def device_auth_ok():
    return True


@app.get('/')
def home(): return render_template('index.html')

@app.get('/api/health')
def health():
    return jsonify(ok=True, gemini_configured=bool(Config.GEMINI_API_KEY),
                   supabase_configured=supabase.enabled, model=Config.GEMINI_MODEL)


@app.post('/api/projects/prepare')
def prepare_project():
    if not device_auth_ok():
        return jsonify(error='Unauthorized'), 401

    audio = request.files.get('audio')

    if not audio or not audio.filename:
        return jsonify(error='Audio file is required'), 400

    data = audio.read()

    if not data:
        return jsonify(error='Empty audio file'), 400

    mime = (
        audio.mimetype
        or mimetypes.guess_type(audio.filename)[0]
        or 'audio/wav'
    ).split(';', 1)[0].strip().lower()

    try:
        result = GeminiService(
            Config.GEMINI_API_KEY,
            Config.GEMINI_MODEL
        ).prepare_project(data, mime)

        return jsonify(ok=True, **result), 200

    except Exception:
        app.logger.exception('Project preparation failed')
        return jsonify(
            ok=False,
            error='Could not prepare project proposal.'
        ), 502
    

@app.post('/api/projects/generate')
def generate_project():
    data = request.get_json(silent=True) or {}

    project_name = str(data.get('project_name', '')).strip()
    project_brief = str(data.get('project_brief', '')).strip()

    # Require explicit confirmation before running the coding agent.
    if data.get('confirmed') is not True:
        return jsonify(
            ok=False,
            error='Project brief must be confirmed before generation.'
        ), 400

    if not project_name or not project_brief:
        return jsonify(
            ok=False,
            error='Project name and brief are required.'
        ), 400

    if len(project_name) > 80 or len(project_brief) > 4000:
        return jsonify(
            ok=False,
            error='Project name or brief is too long.'
        ), 400

    try:
        result = OpenHandsService().start_project(
            project_name,
            project_brief
        )
        return jsonify(result), 202

    except FileExistsError as e:
        return jsonify(ok=False, error=str(e)), 409

    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400

    except OpenHandsServiceError:
        app.logger.exception('OpenHands project generation failed')
        return jsonify(
            ok=False,
            error='Could not start project generation.'
        ), 502

    except Exception:
        app.logger.exception('Unexpected project generation error')
        return jsonify(
            ok=False,
            error='Unexpected server error.'
        ), 500


@app.get('/api/projects/<conversation_id>/status')
def project_status(conversation_id):
    try:
        result = OpenHandsService().get_conversation(
            conversation_id
        )

        return jsonify(
            ok=True,
            conversation_id=conversation_id,
            title=result.get('title'),
            execution_status=result.get('execution_status')
        )

    except OpenHandsServiceError:
        app.logger.exception('Project status check failed')
        return jsonify(
            ok=False,
            error='Could not retrieve project status.'
        ), 502

@app.get('/api/projects/<conversation_id>/report')
def project_report(conversation_id):
    try:
        result = OpenHandsService().get_final_response(conversation_id)

        return jsonify(
            ok=True,
            conversation_id=conversation_id,
            report=result.get('response', '')
        )

    except OpenHandsServiceError:
        app.logger.exception('Project report retrieval failed')
        return jsonify(
            ok=False,
            error='Could not retrieve project report.'
        ), 502

@app.get('/api/projects/<conversation_id>/spoken-summary')
def spoken_project_summary(conversation_id):
    try:
        # Get the final report from OpenHands
        report_data = OpenHandsService().get_final_response(conversation_id)
        report = report_data.get('response', '')

        if not report:
            return jsonify(
                ok=False,
                error='Project report is empty.'
            ), 404

        project_name = request.args.get('name', 'your project')

        # Generate spoken summary using Gemini
        summary = GeminiService(
            Config.GEMINI_API_KEY,
            Config.GEMINI_MODEL
        ).summarize_project_completion(project_name, report)

        # Generate speech using existing TTS logic
        tts_response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={
                "x-goog-api-key": Config.GEMINI_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "model": "gemini-3.8-flash-lite-tts",
                "input": [{
                    "type": "user_input",
                    "content": [{
                        "type": "text",
                        "text": summary,
                        "annotations": [{
                            "type": "speech_metadata",
                            "style": "Calm, clear and natural conversational voice"
                        }]
                    }]
                }],
                "response_format": {"type": "audio"},
                "generation_config": {
                    "speech_config": [
                        {"voice": "Kore"}
                    ]
                }
            },
            timeout=90
        )

        if not tts_response.ok:
            app.logger.error('Project summary TTS failed: %s', tts_response.text[:1000])
            return jsonify(
                ok=False,
                error='Speech generation failed.'
            ), 502

        result = tts_response.json()
        audio_data = result.get("output_audio", {}).get("data")

        if not audio_data:
            for step in result.get("steps", []):
                if step.get("type") == "model_output":
                    for part in step.get("content", []):
                        if part.get("type") == "audio" and part.get("data"):
                            audio_data = part["data"]

        if not audio_data:
            return jsonify(
                ok=False,
                error='No audio returned by Gemini.'
            ), 502

        wav_bytes = base64.b64decode(audio_data)

        return jsonify(
            ok=True,
            conversation_id=conversation_id,
            project_name=project_name,
            summary=summary,
            audio=base64.b64encode(wav_bytes).decode('utf-8'),
            audio_mime='audio/wav'
        ), 200

    except OpenHandsServiceError:
        app.logger.exception('Could not retrieve project report')
        return jsonify(
            ok=False,
            error='Could not retrieve project report.'
        ), 502

    except Exception:
        app.logger.exception('Spoken project summary with audio failed')
        return jsonify(
            ok=False,
            error='Could not generate spoken project summary.'
        ), 502

@app.get('/api/projects/<project_slug>/summary')
def summarize_existing_project(project_slug):
    if not device_auth_ok():
        return jsonify(error='Unauthorized'), 401

    try:
        service = OpenHandsService()
        projects = service.list_projects()

        project = next(
            (
                p for p in projects
                if p.get('project_slug') == project_slug
            ),
            None
        )

        if not project:
            return jsonify(
                ok=False,
                error='Project not found.'
            ), 404

        project_file = Path(project['project_path']) / 'index.html'

        if not project_file.is_file():
            return jsonify(
                ok=False,
                error='Project source file not found.'
            ), 404

        source = project_file.read_text(
            encoding='utf-8',
            errors='replace'
        )[:30000]

        summary = GeminiService(
            Config.GEMINI_API_KEY,
            Config.GEMINI_MODEL
        ).summarize_project_contents(
            project['project_name'],
            source
        )

        wav_bytes = generate_tts_audio(summary)

        return jsonify(
            ok=True,
            project_name=project['project_name'],
            project_slug=project['project_slug'],
            summary=summary,
            audio=base64.b64encode(wav_bytes).decode('utf-8')
        ), 200

    except Exception:
        app.logger.exception('Project content summarization failed')
        return jsonify(
            ok=False,
            error='Could not summarize project.'
        ), 500

@app.get('/api/projects')
def list_projects():
    if not device_auth_ok():
        return jsonify(error='Unauthorized'), 401

    try:
        projects = OpenHandsService().list_projects()

        return jsonify(
            ok=True,
            projects=projects,
            count=len(projects)
        ), 200

    except Exception:
        app.logger.exception('Project listing failed')
        return jsonify(
            ok=False,
            error='Could not retrieve projects.'
        ), 500

@app.get('/api/items')
def get_items():
    try: return jsonify(supabase.list_items())
    except Exception as e:
        app.logger.exception('Supabase list failed')
        return jsonify(error='Could not load items', detail=str(e)),502

@app.get('/api/search')
def search_items():
    query = request.args.get('q', '').strip()
    item_type = request.args.get('type', '').strip() or None

    try:
        limit = int(request.args.get('limit', 10))
        limit = max(1, min(limit, 50))

        if not query:
            return jsonify(error="Missing search query. Use ?q=your_query"), 400

        results = supabase.search_items(
            query=query,
            limit=limit,
            item_type=item_type
        )

        return jsonify({
            "ok": True,
            "query": query,
            "count": len(results),
            "results": results
        })

    except Exception as e:
        app.logger.exception("Search failed")
        return jsonify(error="Search failed", detail=str(e)), 502

@app.post('/api/ask')
def ask_memory():
    data = request.get_json(silent=True) or {}
    question = str(data.get('question', '')).strip()

    if not question:
        return jsonify(error="Question is required"), 400

    try:
        # Retrieve relevant stored memories
        matches = supabase.search_items(
            query=question,
            limit=10
        )

        if not matches:
            return jsonify(
                ok=True,
                answer="I don't have a stored memory about that.",
                sources=[],
                source_count=0
            )

        # Keep the context compact for the model
        context = [
            {
                "title": item.get("title"),
                "type": item.get("item_type"),
                "summary": item.get("summary"),
                "due": item.get("due"),
                "start": item.get("start"),
                "tags": item.get("tags", [])
            }
            for item in matches
        ]

        prompt = f"""
You are the memory assistant inside Pala Note.

Answer the user's question using ONLY the stored memories below.

Rules:
- Do not invent personal information or events.
- If the memories do not contain enough information, say so.
- Keep answers concise and conversational.
- Do not treat guesses as facts.

Stored memories:
{json.dumps(context, ensure_ascii=False)}

Question:
{question}
"""

        client = genai.Client(api_key=Config.GEMINI_API_KEY)

        response = client.models.generate_content(
            model=Config.GEMINI_MODEL,
            contents=prompt
        )

        return jsonify(
            ok=True,
            question=question,
            answer=response.text or "I couldn't generate an answer.",
            sources=[
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "type": item.get("item_type")
                }
                for item in matches
            ],
            source_count=len(matches)
        )

    except Exception as e:
        app.logger.exception("Memory query failed")
        return jsonify(
            error="Could not answer the question",
            detail=str(e)
        ), 502


def generate_tts_audio(text):
    """Generate WAV audio from text using Gemini TTS."""

    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        headers={
            "x-goog-api-key": Config.GEMINI_API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "model": "gemini-3.8-flash-lite-tts",
            "input": [{
                "type": "user_input",
                "content": [{
                    "type": "text",
                    "text": text,
                    "annotations": [{
                        "type": "speech_metadata",
                        "style": "Calm, clear and natural conversational voice"
                    }]
                }]
            }],
            "response_format": {"type": "audio"},
            "generation_config": {
                "speech_config": [
                    {"voice": "Kore"}
                ]
            }
        },
        timeout=90
    )

    if not response.ok:
        raise RuntimeError(
            f"Gemini TTS failed: {response.text[:1000]}"
        )

    result = response.json()
    audio_data = result.get("output_audio", {}).get("data")

    if not audio_data:
        for step in result.get("steps", []):
            if step.get("type") == "model_output":
                for part in step.get("content", []):
                    if part.get("type") == "audio" and part.get("data"):
                        audio_data = part["data"]

    if not audio_data:
        raise RuntimeError("Gemini returned no audio data.")

    return base64.b64decode(audio_data)

@app.post('/api/tts')
@app.post('/api/tts')
def text_to_speech():
    data = request.get_json(silent=True) or {}
    text = str(data.get('text', '')).strip()

    if not text:
        return jsonify(error="Text is required"), 400

    try:
        wav_bytes = generate_tts_audio(text)

        return send_file(
            BytesIO(wav_bytes),
            mimetype="audio/wav",
            as_attachment=True,
            download_name="pala_note_reply.wav"
        )

    except Exception as e:
        app.logger.exception("TTS failed")
        return jsonify(
            error="TTS processing failed",
            detail=str(e)
        ), 502


@app.post('/api/ask-audio')
def ask_audio():
    data = request.get_json(silent=True) or {}
    question = str(data.get('question', '')).strip()

    if not question:
        return jsonify(error="Question is required"), 400

    try:
        # 1. Retrieve relevant memories
        matches = supabase.search_items(
            query=question,
            limit=10
        )

        context = [
            {
                "title": item.get("title"),
                "type": item.get("item_type"),
                "summary": item.get("summary"),
                "due": item.get("due"),
                "start": item.get("start"),
                "tags": item.get("tags", [])
            }
            for item in matches
        ]

        # 2. Generate an answer using Gemini
        if context:
            prompt = f"""
You are Pala Note, a personal memory assistant.

Answer using ONLY the stored memories below.

Rules:
- Never invent personal information.
- If the information is unavailable, say so.
- Keep the answer short and conversational.

Stored memories:
{json.dumps(context, ensure_ascii=False)}

Question:
{question}
"""
        else:
            prompt = f"""
You are Pala Note, a personal memory assistant.
You have no relevant stored memories for this question.
Politely explain that you don't remember this information.

Question: {question}
"""

        client = genai.Client(api_key=Config.GEMINI_API_KEY)

        answer_response = client.models.generate_content(
            model=Config.GEMINI_MODEL,
            contents=prompt
        )

        answer = answer_response.text or "I couldn't generate an answer."

        # 3. Convert the answer into speech
        tts_response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={
                "x-goog-api-key": Config.GEMINI_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "model": "gemini-3.8-flash-lite-tts",
                "input": [{
                    "type": "user_input",
                    "content": [{
                        "type": "text",
                        "text": answer,
                        "annotations": [{
                            "type": "speech_metadata",
                            "style": "Calm, clear and natural conversational voice"
                        }]
                    }]
                }],
                "response_format": {"type": "audio"},
                "generation_config": {
                    "speech_config": [
                        {"voice": "Kore"}
                    ]
                }
            },
            timeout=90
        )

        if not tts_response.ok:
            raise RuntimeError(
                f"TTS failed: {tts_response.status_code} | {tts_response.text}"
            )

        tts_result = tts_response.json()
        audio_data = tts_result.get("output_audio", {}).get("data")

        if not audio_data:
            for step in tts_result.get("steps", []):
                if step.get("type") == "model_output":
                    for part in step.get("content", []):
                        if part.get("type") == "audio":
                            audio_data = part.get("data")
                            if audio_data:
                                break

        if not audio_data:
            raise RuntimeError("Gemini returned no audio data")

        # 4. Return answer and audio together
        return jsonify(
            ok=True,
            question=question,
            answer=answer,
            sources=[
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "type": item.get("item_type")
                }
                for item in matches
            ],
            source_count=len(matches),
            audio_base64=audio_data,
            audio_format="wav"
        )

    except Exception as e:
        app.logger.exception("Ask-audio failed")
        return jsonify(
            error="Could not process voice query",
            detail=str(e)
        ), 502

@app.post('/api/audio')
def audio_upload():
    if not device_auth_ok(): return jsonify(error='Unauthorized'),401
    f=request.files.get('audio')
    if not f or not f.filename: return jsonify(error="Expected multipart file field 'audio'"),400
    filename=secure_filename(f.filename)
    mime=f.mimetype or mimetypes.guess_type(filename)[0] or 'audio/wav'
    data=f.read()
    if not data: return jsonify(error='Empty audio file'),400
    try:
        result=GeminiService(Config.GEMINI_API_KEY,Config.GEMINI_MODEL).analyze_audio(data,mime)
        saved = {}
        duplicate = False
        saved_count = 0

        if supabase.enabled:
            audio_hash = hashlib.sha256(data).hexdigest()
            created_at = datetime.now(timezone.utc).isoformat()

            saved = supabase.save_note_recording(
                audio_hash=audio_hash,
                transcript=result['transcript'],
                created_at=created_at,
                items=result['items']
            )

            duplicate = bool(saved.get('duplicate', False))

            if not duplicate:
                saved_count = len(result['items'])
        return jsonify(
                ok=True,
                transcript=result['transcript'],
                extracted_items=result['items'],
                saved_count=saved_count,
                duplicate=duplicate,
                storage='supabase' if supabase.enabled else 'not configured'
            )
    except Exception as e:
        app.logger.exception('Audio processing failed')
        return jsonify(error='Audio processing failed',detail=str(e)),502

@app.post('/api/voice-command')
def voice_command():
    if not device_auth_ok():
        return jsonify(error='Unauthorized'), 401

    f = request.files.get('audio')

    if not f or not f.filename:
        return jsonify(error="Expected multipart file field 'audio'"), 400

    filename = secure_filename(f.filename)
    uploaded_mime = (f.mimetype or "").split(";", 1)[0].strip().lower()
    guessed_mime = mimetypes.guess_type(filename)[0]

    mime = (
        uploaded_mime
        if uploaded_mime.startswith("audio/")
        else guessed_mime
        if guessed_mime and guessed_mime.startswith("audio/")
        else "audio/wav"
    )
    print("MIME BEFORE READ:", mime)
    print("FILENAME:", filename)
    data = f.read()
    print("Detected audio MIME:", mime)
    print("Uploaded filename:", filename)

    if not data:
        return jsonify(error='Empty audio file'), 400

    try:
        gemini = GeminiService(Config.GEMINI_API_KEY, Config.GEMINI_MODEL)

        transcript = gemini.transcribe_audio(data, mime)
        intent = gemini.detect_voice_intent(transcript)

        result = {
            'ok': True,
            'transcript': transcript,
            'intent': intent
        }

        if intent == "recall_project":
            service = OpenHandsService()
            projects = service.list_projects()

            project_slug = gemini.identify_project(
                transcript,
                projects
            )

            if not project_slug:
                result["project_found"] = False
                result["message"] = "I couldn't identify which project you mean."
                return jsonify(result), 200

            project = service.get_project_by_slug(project_slug)

            if not project:
                result["project_found"] = False
                result["message"] = "The selected project could not be found."
                return jsonify(result), 200

            result.update({
                "project_found": True,
                "project_name": project["project_name"],
                "project_slug": project["project_slug"]
            })

            source_file = Path(project['project_path']) / 'index.html'

            if source_file.is_file():
                source = source_file.read_text(
                    encoding='utf-8',
                    errors='replace'
                )[:30000]

                summary = GeminiService(
                    Config.GEMINI_API_KEY,
                    Config.GEMINI_MODEL
                ).summarize_project_contents(
                    project['project_name'],
                    source
                )

                wav_bytes = generate_tts_audio(summary)

                result.update({
                    "summary": summary,
                    "audio": base64.b64encode(wav_bytes).decode('utf-8')
                })
            else:
                result["summary"] = "I couldn't find the source files for this project."

        return jsonify(result), 200

    except Exception as e:
        app.logger.exception('Voice command processing failed')
        return jsonify(
            error='Voice command processing failed',
            detail=str(e)
        ), 502


@app.errorhandler(413)
def too_large(_): return jsonify(error=f'Upload exceeds {Config.MAX_UPLOAD_MB} MB limit'),413

if __name__=='__main__':
    print(f'Pala Note backend running at http://{Config.HOST}:{Config.PORT}')
    print(f'Gemini model: {Config.GEMINI_MODEL} | Supabase configured: {supabase.enabled}')
    app.run(host=Config.HOST,port=Config.PORT,debug=Config.DEBUG)