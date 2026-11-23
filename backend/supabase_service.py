import requests


class SupabaseService:
    def __init__(self, url, key, table):
        self.url = url.rstrip('/')
        self.key = key
        self.table = table
        self.enabled = bool(self.url and self.key)

    def headers(self):
        return {
            'apikey': self.key,
            'Authorization': f'Bearer {self.key}',
            'Content-Type': 'application/json'
        }

    def list_items(self, limit=100):
        if not self.enabled:
            return []

        r = requests.get(
            f'{self.url}/rest/v1/{self.table}',
            headers=self.headers(),
            params={
                'select': '*',
                'order': 'created_at.desc',
                'limit': limit
            },
            timeout=15
        )

        if not r.ok:
            raise RuntimeError(
                f'Supabase list failed: {r.status_code} | {r.text}'
            )

        return r.json()

    def search_items(self, query, limit=10, item_type=None):
        if not self.enabled:
            return []

        query = (query or "").strip().lower()
        if not query:
            return []

        # Fetch recent items; ranking is done locally for V1.
        r = requests.get(
            f'{self.url}/rest/v1/{self.table}',
            headers=self.headers(),
            params={
                'select': '*',
                'order': 'created_at.desc',
                'limit': 200
            },
            timeout=15
        )

        if not r.ok:
            raise RuntimeError(
                f'Supabase search failed: {r.status_code} | {r.text}'
            )

        items = r.json()

        # Allow type-based queries.
        type_aliases = {
            'tasks': 'task',
            'task': 'task',
            'reminders': 'task',
            'appointments': 'appointment',
            'appointment': 'appointment',
            'memories': 'memory',
            'memory': 'memory',
            'ideas': 'memory',
            'idea': 'memory'
        }

        if item_type is None:
            item_type = type_aliases.get(query)

        if item_type:
            items = [
                item for item in items
                if item.get('item_type') == item_type
            ]

        query_words = [
            word for word in query.split()
            if len(word) > 1
        ]

        scored = []

        for item in items:
            title = str(item.get('title') or '').lower()
            summary = str(item.get('summary') or '').lower()
            transcript = str(item.get('transcript') or '').lower()
            tags = ' '.join(item.get('tags') or []).lower()
            kind = str(item.get('item_type') or '').lower()

            searchable = f'{title} {summary} {transcript} {tags} {kind}'

            score = 0

            # Exact phrase matches.
            if query in title:
                score += 10

            if query in summary:
                score += 5

            if query in transcript:
                score += 2

            if query in tags:
                score += 4

            # Individual keyword matches.
            for word in query_words:
                if word in title:
                    score += 4
                if word in summary:
                    score += 2
                if word in transcript:
                    score += 1
                if word in tags:
                    score += 3

            if score > 0:
                scored.append((score, item))

        scored.sort(
            key=lambda entry: (
                entry[0],
                entry[1].get('created_at', '')
            ),
            reverse=True
        )

        return [
            item for score, item in scored[:limit]
        ]

    @staticmethod
    def _combine_date_time(details):
        date = details.get('date')
        time = details.get('time')

        parts = [
            str(value).strip()
            for value in (date, time)
            if value and str(value).strip().lower() != 'null'
        ]

        return ' '.join(parts) if parts else None

    def _prepare_items(self, items, transcript):
        rows = []

        for item in items:
            if not isinstance(item, dict):
                continue

            raw_kind = str(
                item.get('kind') or 'memory'
            ).strip().lower()

            # Supabase permits only task, appointment and memory.
            if raw_kind in ('task', 'reminder'):
                item_type = 'task'
            elif raw_kind == 'appointment':
                item_type = 'appointment'
            else:
                item_type = 'memory'

            details = item.get('details')
            if not isinstance(details, dict):
                details = {}

            content = str(
                item.get('content') or item.get('summary') or ''
            ).strip()

            title = str(item.get('title') or '').strip()

            if not title:
                title = content[:70] or 'Voice note'

            # Preserve explicit tags and useful extracted details.
            raw_tags = item.get('tags') or []
            if isinstance(raw_tags, str):
                raw_tags = [raw_tags]

            tags = [
                str(tag).strip()
                for tag in raw_tags
                if str(tag).strip()
            ]

            people = details.get('people') or []
            if isinstance(people, list):
                tags.extend(
                    f'person:{person}'
                    for person in people
                    if person
                )

            place = details.get('place')
            if place:
                tags.append(f'place:{place}')

            priority = details.get('priority')
            if priority:
                tags.append(f'priority:{priority}')

            if raw_kind in ('idea', 'other'):
                tags.append(raw_kind)

            when = self._combine_date_time(details)

            rows.append({
                'type': item_type,
                'title': title,
                'summary': content or title,
                'due': when if item_type == 'task' else None,
                'start': when if item_type == 'appointment' else None,
                'tags': tags
            })

        return rows

    def save_note_recording(
        self,
        audio_hash,
        transcript,
        created_at,
        items
    ):
        if not self.enabled:
            return {}

        prepared_items = self._prepare_items(items, transcript)

        payload = {
            'p_audio_hash': audio_hash,
            'p_transcript': transcript,
            'p_created_at': created_at,
            'p_items': prepared_items
        }

        r = requests.post(
            f'{self.url}/rest/v1/rpc/save_note_recording',
            headers=self.headers(),
            json=payload,
            timeout=30
        )

        if not r.ok:
            raise RuntimeError(
                f'Supabase RPC failed: {r.status_code} | {r.text}'
            )

        result = r.json()

        return result if isinstance(result, dict) else {}