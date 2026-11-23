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
        if not key:
            raise RuntimeError('GEMINI_API_KEY is missing')
        self.client = genai.Client(api_key=key)
        self.model = model

    def analyze_audio(self, data, mime):
        part = types.Part.from_bytes(data=data, mime_type=mime)
        response = self.client.models.generate_content(
            model=self.model,
            contents=[PROMPT, part],
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
                temperature=0.2
            )
        )
        raw = (response.text or '').strip()
        if not raw:
            raise ValueError('Gemini returned empty output')
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            raw = re.sub(r'^```(?:json)?|```$', '', raw, flags=re.MULTILINE).strip()
            obj = json.loads(raw)
        if not isinstance(obj, dict) or not isinstance(obj.get('items', []), list):
            raise ValueError('Gemini response has unexpected JSON shape')
        normalized = []
        for item in obj.get('items', []):
            if not isinstance(item, dict):
                continue
            normalized.append({
                'kind': str(item.get('kind') or 'memory')[:40],
                'title': str(item.get('title') or '')[:200],
                'content': str(item.get('content') or '')[:10000],
                'details': item.get('details') if isinstance(item.get('details'), dict) else {},
                'source': 'audio'
            })
        return {'transcript': str(obj.get('transcript') or ''), 'items': normalized}

    def detect_voice_intent(self, transcript):
      prompt = f"""
  You are the intent classifier for Pala Note, a personal voice assistant.

  Classify the user's transcript into exactly one intent:

  - "save_memory": The user is sharing information, a thought, task, reminder, idea, or event to save.
  - "recall_project": The user is asking about an existing project they previously built.
  - "generate_project": The user wants to create, build, or generate a new software project.
  - "general": Anything else.

  TRANSCRIPT:
  {transcript}

  Rules:
  - Return ONLY one valid JSON object.
  - Format: {{"intent": "save_memory"}}
  - Do not explain your classification.
  - Do not invent intent that is not clearly expressed.
  """
      response = self.client.models.generate_content(
          model=self.model,
          contents=prompt,
          config=types.GenerateContentConfig(
              response_mime_type="application/json",
              temperature=0
          )
      )

      raw = (response.text or "").strip()

      if not raw:
          raise ValueError("Gemini returned empty intent output")

      result = json.loads(raw)
      intent = result.get("intent")

      allowed = {
          "save_memory",
          "recall_project",
          "generate_project",
          "general"
      }

      if intent not in allowed:
          raise ValueError(f"Invalid voice intent: {intent}")

      return intent

    def identify_project(self, transcript, projects):
      project_data = [
          {
              "name": project.get("project_name"),
              "slug": project.get("project_slug")
          }
          for project in projects
      ]

      prompt = f"""
  You are Pala Note, a project-recall assistant.

  Identify which existing project the user is referring to.

  USER REQUEST:
  {transcript}

  AVAILABLE PROJECTS:
  {json.dumps(project_data, indent=2)}

  Rules:
  - Select a project only when the request clearly refers to one.
  - Use project names and slugs as evidence.
  - If no project clearly matches, return null.
  - Never invent a project.
  - Return ONLY valid JSON in this format:
    {{"project_slug": "expense-tracker"}}
  - If uncertain or no match:
    {{"project_slug": null}}
  """

      response = self.client.models.generate_content(
          model=self.model,
          contents=prompt,
          config=types.GenerateContentConfig(
              response_mime_type="application/json",
              temperature=0
          )
      )

      raw = (response.text or "").strip()

      if not raw:
          raise ValueError("Gemini returned empty project identification")

      result = json.loads(raw)
      slug = result.get("project_slug")

      valid_slugs = {
          project.get("project_slug")
          for project in projects
      }

      if slug not in valid_slugs:
          return None

      return slug


    def transcribe_audio(self, data, mime):
      part = types.Part.from_bytes(data=data, mime_type=mime)

      response = self.client.models.generate_content(
          model=self.model,
          contents=[
              """
              Transcribe the user's audio faithfully.

              Return only the exact spoken words.
              Do not summarize, analyze, extract memories, or add commentary.
              """
              ,
              part
          ],
          config=types.GenerateContentConfig(
              temperature=0
          )
      )

      transcript = (response.text or "").strip()

      if not transcript:
          raise ValueError("Gemini returned empty transcription")

      return transcript
    
    def prepare_project(self, data, mime):
        prompt = """
You are Pala Note's project planning assistant.

Listen to the user's audio and prepare a project proposal.

Return ONLY valid JSON:
{
    "transcript": "Faithful transcript of the audio",
    "project_name": "Short project name",
    "project_brief": "Clear description of the requested project"
}

Rules:
- Preserve the user's actual idea.
- Do not invent requirements or features.
- Keep the project brief concise.
- The project is a quick faculty demonstration prototype.
- The final implementation will use one index.html file.
- It must use HTML, CSS and vanilla JavaScript only.
- Do not plan frameworks, installations or external dependencies.
- Return valid JSON only.
"""

        part = types.Part.from_bytes(data=data, mime_type=mime)

        response = self.client.models.generate_content(
            model=self.model,
            contents=[prompt, part],
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
                temperature=0.2
            )
        )

        raw = (response.text or '').strip()

        if not raw:
            raise ValueError('Gemini returned empty output')

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError('Gemini returned invalid project JSON')

        if not isinstance(result, dict):
            raise ValueError('Unexpected Gemini response')

        project_name = str(result.get('project_name') or '').strip()
        project_brief = str(result.get('project_brief') or '').strip()

        if not project_name or not project_brief:
            raise ValueError('Project name or brief is missing')

        return {
            'transcript': str(result.get('transcript') or ''),
            'project_name': project_name[:80],
            'project_brief': project_brief[:4000]
        }

    def summarize_project_completion(self, project_name, report):
        prompt = f"""
You are Pala Note, a friendly voice assistant.

A project has just been completed by an AI coding agent.

PROJECT NAME:
{project_name}

AGENT REPORT:
{report}

Create a short spoken announcement for the user.

Rules:
- Start by announcing that the project is ready.
- Tell the user that the files have been created and they can check them now.
- Explain the main features in simple language.
- Sound natural when spoken aloud.
- Do not read Markdown, code, file formatting, or bullet points aloud.
- Do not invent features that are not mentioned in the report.
- Keep it under 80 words.
- Output plain text only.
"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.4
            )
        )

        text = (response.text or '').strip()

        if not text:
            raise ValueError('Gemini returned empty project summary')

        return text

    def summarize_project_contents(self, project_name, project_content):
        prompt = f"""
You are Pala Note, a personal voice assistant.

The user wants to recall an existing project.

PROJECT NAME:
{project_name}

PROJECT SOURCE CODE:
{project_content}

Describe what this project actually does.

Rules:
- Explain the purpose of the project.
- Describe its main features.
- Mention important interactions or functionality.
- Use simple, natural language suitable for speaking aloud.
- Do not claim features that are not supported by the source code.
- Do not read code, HTML, CSS, or technical syntax aloud.
- Keep the answer under 100 words.
- Output plain text only.
"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3
            )
        )

        text = (response.text or '').strip()

        if not text:
            raise ValueError('Gemini returned empty project summary')

        return text

    def answer_project_question(self, project_name, project_content, question):
        question = str(question or '').strip()
        if not question:
            raise ValueError('A project question is required')
        if not project_content:
            raise ValueError('Project source content is empty')

        prompt = f"""
    You are Pala Note, a personal project-memory assistant.

    Answer the user's question about their existing project using the
    provided project source code as your primary source.

    PROJECT NAME:
    {project_name}

    PROJECT SOURCE:
    {project_content[:30000]}

    USER QUESTION:
    {question}

    RULES:
    - Answer directly and conversationally.
    - Use only information supported by the provided source.
    - If the source does not contain the answer, clearly say you cannot determine it from the available project files.
    - Do not invent libraries, databases, features, design decisions, or implementation details.
    - Keep the answer concise and suitable for being spoken aloud.
    """

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3
            )
        )

        answer = (response.text or "").strip()

        if not answer:
            raise ValueError("Gemini returned an empty project answer")

        return answer