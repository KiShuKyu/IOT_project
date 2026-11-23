import json
import re
from google import genai
from google.genai import types

PROMPT = """
You are Pala Note, a personal voice-memory assistant.

Your job is to transcribe audio faithfully and extract useful information
that the user may want to remember or retrieve later.

Return ONLY valid JSON in this exact structure:

{
  "transcript": "Complete faithful transcript",
  "items": [
    {
      "kind": "memory",
      "title": "Short descriptive title",
      "content": "Clear and concise description",
      "details": {
        "date": null,
        "time": null,
        "people": [],
        "place": null,
        "priority": null
      }
    }
  ]
}

EXTRACTION RULES:

1. MEMORY
Extract useful personal facts, preferences, identity details,
background information, ongoing projects, and important context.

Examples:
- My name is Krishna.
- I am building a project called Pala Note.
- I am learning Python and Django.
- My project uses ESP32 and Gemini.

2. TASK
Extract actions the user intends or needs to complete.

Examples:
- I need to test the audio upload system.
- I have to finish my college assignment.
- I need to debug my Python application.

3. APPOINTMENT
Extract scheduled events, meetings, classes, and commitments.

4. IDEA
Extract new ideas, concepts, features, and possible improvements.

5. REMINDER
Extract things the user explicitly wants to remember or be
reminded about.

6. OTHER
Extract useful information that does not fit the categories above.

IMPORTANT:
- Choose exactly ONE kind per item:
  memory, task, appointment, idea, reminder, or other.
- Treat meaningful personal statements as memories, even when
  the user does not explicitly say "remember this".
- Extract multiple independent items when appropriate.
- Do not create items for greetings, filler words, or meaningless
  conversation.
- Do not invent information or assume unstated facts.
- Preserve the user's actual meaning.
- Keep the transcript faithful to the original audio.
- Include dates, times, people, places and priorities only when
  supported by the audio.
- Do not guess calendar dates for relative expressions such as
  "tomorrow" when their reference date is unavailable.
- Return an empty items array only when the audio contains no
  meaningful information worth remembering.

The transcript must always be returned, even if items is empty.
Return valid JSON only. Do not include Markdown or explanations.
"""

class GeminiService:
    def __init__(self, key, model):
        if not key: raise RuntimeError('GEMINI_API_KEY is missing')
        self.client = genai.Client(api_key=key)
        self.model = model

    def analyze_audio(self, data, mime):
        part = types.Part.from_bytes(data=data, mime_type=mime)
        response = self.client.models.generate_content(
            model=self.model,
            contents=[PROMPT, part],
            config=types.GenerateContentConfig(response_mime_type='application/json', temperature=0.2)
        )
        raw = (response.text or '').strip()
        if not raw: raise ValueError('Gemini returned empty output')
        try: obj = json.loads(raw)
        except json.JSONDecodeError:
            raw = re.sub(r'^```(?:json)?|```$', '', raw, flags=re.MULTILINE).strip()
            obj = json.loads(raw)
        if not isinstance(obj, dict) or not isinstance(obj.get('items', []), list):
            raise ValueError('Gemini response has unexpected JSON shape')
        normalized=[]
        for item in obj.get('items', []):
            if not isinstance(item, dict): continue
            normalized.append({
                'kind': str(item.get('kind') or 'memory')[:40],
                'title': str(item.get('title') or '')[:200],
                'content': str(item.get('content') or '')[:10000],
                'details': item.get('details') if isinstance(item.get('details'),dict) else {},
                'source': 'audio'
            })
        return {'transcript': str(obj.get('transcript') or ''), 'items': normalized}
