from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from memory_context_research.models import RepoState


def load_state(path: str | Path) -> dict[str, RepoState]:
    state_path = Path(path)
    if not state_path.exists():
        return {}
    data = json.loads(state_path.read_text(encoding="utf-8"))
    return {name: RepoState(**payload) for name, payload in data.items()}


def save_state(path: str | Path, state: dict[str, RepoState]) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {name: asdict(repo_state) for name, repo_state in state.items()}
    state_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
