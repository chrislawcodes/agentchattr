import json
import logging
from pathlib import Path
from store import MessageStore

log = logging.getLogger(__name__)

class ProjectManager:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.projects_dir = self.data_dir / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.current_project = "default"
        self._stores: dict[str, MessageStore] = {}
        
        # Ensure default project exists
        self._ensure_project("default")

    def _ensure_project(self, name: str):
        project_path = self.projects_dir / name
        project_path.mkdir(parents=True, exist_ok=True)
        log_path = project_path / "agentchattr_log.jsonl"
        
        # Handle migration for default project if needed
        if name == "default":
            legacy_log = self.data_dir / "agentchattr_log.jsonl"
            if legacy_log.exists() and not log_path.exists():
                log_path.write_bytes(legacy_log.read_bytes())
                # Also migrate todos if they exist
                legacy_todos = self.data_dir / "todos.json"
                if legacy_todos.exists():
                    (project_path / "todos.json").write_bytes(legacy_todos.read_bytes())

        if name not in self._stores:
            self._stores[name] = MessageStore(str(log_path))

    def get_store(self, name: str | None = None) -> MessageStore:
        name = name or self.current_project
        self._ensure_project(name)
        return self._stores[name]

    def list_projects(self) -> list[str]:
        return [p.name for p in self.projects_dir.iterdir() if p.is_dir()]

    def switch_project(self, name: str) -> MessageStore:
        self._ensure_project(name)
        self.current_project = name
        return self.get_store(name)
