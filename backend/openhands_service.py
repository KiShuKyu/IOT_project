import re
from pathlib import Path
from urllib.parse import quote

import requests

from config import Config
import json
from datetime import datetime, timezone


class OpenHandsServiceError(Exception):
    """Raised when communication with OpenHands fails."""


class OpenHandsService:

    def __init__(self):
        self.base_url = Config.OPENHANDS_URL.rstrip("/")
        self.api_key = Config.OPENHANDS_API_KEY
        self.profile_id = Config.OPENHANDS_AGENT_PROFILE_ID
        self.projects_root = Path(Config.PROJECTS_ROOT).expanduser()
        self.registry_file = self.projects_root / "projects.json"   

        self.session = requests.Session()
        self.session.headers.update({
            "X-Session-API-Key": self.api_key,
            "Content-Type": "application/json"
        })

    def _request(self, method, endpoint, **kwargs):
        if not self.api_key:
            raise OpenHandsServiceError(
                "OPENHANDS_API_KEY is missing from .env"
            )

        try:
            response = self.session.request(
                method,
                f"{self.base_url}{endpoint}",
                timeout=kwargs.pop("timeout", 30),
                **kwargs
            )
        except requests.RequestException as exc:
            raise OpenHandsServiceError(
                f"Could not connect to OpenHands: {exc}"
            ) from exc

        if not response.ok:
            raise OpenHandsServiceError(
                f"OpenHands returned HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise OpenHandsServiceError(
                "OpenHands returned an invalid JSON response."
            ) from exc

    def check_connection(self):
        """Check server availability and authentication."""
        info = self._request("GET", "/server_info")

        return {
            "ok": True,
            "title": info.get("title"),
            "version": info.get("version")
        }

    def _create_workspace(self, project_name):
        """Create a new, empty project workspace."""
        slug = re.sub(
            r"[^a-z0-9]+",
            "-",
            project_name.lower()
        ).strip("-")

        if not slug:
            raise ValueError("Invalid project name.")

        root = self.projects_root.resolve()
        root.mkdir(parents=True, exist_ok=True)

        project_dir = (root / slug).resolve()

        if project_dir.parent != root:
            raise ValueError("Invalid project workspace path.")

        if project_dir.exists() and any(project_dir.iterdir()):
            raise FileExistsError(
                f"Project workspace already exists: {project_dir}"
            )

        project_dir.mkdir(parents=True, exist_ok=True)

        return slug, project_dir

    def _load_registry(self):
        """Load locally saved project metadata."""
        if not self.registry_file.exists():
            return []

        with self.registry_file.open("r", encoding="utf-8") as f:
            projects = json.load(f)

        if not isinstance(projects, list):
            raise OpenHandsServiceError("Project registry has an invalid format.")

        return projects

    def _save_registry(self, projects):
        """Save project metadata locally."""
        self.projects_root.mkdir(parents=True, exist_ok=True)

        with self.registry_file.open("w", encoding="utf-8") as f:
            json.dump(projects, f, indent=4, ensure_ascii=False)

    def _register_project(self, project):
        """Add a project to the local registry."""
        projects = self._load_registry()
        projects.append(project)
        self._save_registry(projects)

    def list_projects(self):
        """Return registered projects whose workspaces still exist."""
        projects = self._load_registry()

        existing_projects = [
            project for project in projects
            if Path(project.get("project_path", "")).exists()
        ]

        return sorted(
            existing_projects,
            key=lambda project: project.get("created_at", ""),
            reverse=True
        )

    def find_projects(self, query):
        """Search registered projects by name or project slug."""
        projects = self.list_projects()
        query = query.strip().lower()

        if not query:
            return projects

        matches = [
            project for project in projects
            if query in project.get("project_name", "").lower()
            or query in project.get("project_slug", "").lower()
        ]

        return matches

    def get_project_by_slug(self, slug):
        """Return a registered project matching its exact slug."""
        projects = self.list_projects()

        for project in projects:
            if project.get("project_slug") == slug:
                return project

        return None

    def import_existing_projects(self):
        """Import existing local workspaces into the project registry."""
        projects = self._load_registry()
        registered_slugs = {
            project.get("project_slug") for project in projects
        }

        self.projects_root.mkdir(parents=True, exist_ok=True)

        imported = []

        for folder in self.projects_root.iterdir():
            if not folder.is_dir():
                continue

            if folder.name in registered_slugs:
                continue

            index_file = folder / "index.html"

            if not index_file.exists():
                continue

            created_at = datetime.fromtimestamp(
                index_file.stat().st_mtime,
                timezone.utc
            ).isoformat()

            project = {
                "project_name": folder.name.replace("-", " ").title(),
                "project_slug": folder.name,
                "conversation_id": None,
                "project_brief": "",
                "created_at": created_at,
                "project_path": str(folder.resolve())
            }

            projects.append(project)
            imported.append(project)

        self._save_registry(projects)

        return imported



    def start_project(self, project_name, project_brief):
        """
        Create an OpenHands conversation and start the coding agent.

        Call this only after the user has confirmed the project brief.
        """
        if not self.profile_id:
            raise OpenHandsServiceError(
                "OPENHANDS_AGENT_PROFILE_ID is missing."
            )

        if not project_name.strip() or not project_brief.strip():
            raise ValueError("Project name and brief are required.")

        slug, project_dir = self._create_workspace(project_name)


        agent_message = f"""
Create a simple demonstration project based on this idea.

PROJECT: {project_name}

IDEA:
{project_brief}

Requirements:
- Create a single self-contained index.html file.
- Use only HTML, CSS, and vanilla JavaScript.
- No frameworks, installations, or external dependencies.
- Make it visually clean and interactive where appropriate.
- Focus on demonstrating the core functionality, not building a complete product.
- Keep the implementation simple and fast.
- Do not create additional files.
- Do not over-engineer.

When finished, briefly report what you created.
"""


        payload = {
            "workspace": {
                "working_dir": str(project_dir)
            },
            "agent_profile_id": self.profile_id,
            "conversation_runtime": "local",
            "max_iterations": 15,
            "stuck_detection": True,
            "autotitle": True,
            "tags": {
                "source": "palanote",
                "project": slug
            },
            "initial_message": {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": agent_message
                    }
                ],
                "run": True
            }
        }

        result = self._request(
            "POST",
            "/api/conversations",
            json=payload,
            timeout=60
        )

        conversation_id = result.get("id")

        if not conversation_id:
            raise OpenHandsServiceError(
                "OpenHands did not return a conversation ID."
            )
        project_data = {
            "project_name": project_name,
            "project_slug": slug,
            "conversation_id": conversation_id,
            "project_brief": project_brief,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "project_path": str(project_dir)
        }

        self._register_project(project_data)

        return {
            "ok": True,
            "project_name": project_name,
            "project_slug": slug,
            "project_path": str(project_dir),
            "conversation_id": conversation_id,
            "execution_status": result.get("execution_status", "unknown")
        }

    def get_conversation(self, conversation_id):
        """Retrieve the current conversation status."""
        safe_id = quote(str(conversation_id), safe="")

        return self._request(
            "GET",
            f"/api/conversations/{safe_id}"
        )

    def get_final_response(self, conversation_id):
        safe_id = quote(str(conversation_id), safe="")

        return self._request(
            "GET",
            f"/api/conversations/{safe_id}/agent_final_response"
        )