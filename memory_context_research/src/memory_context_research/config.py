from __future__ import annotations

from pathlib import Path

import yaml

from memory_context_research.models import RepoConfig, ResearchConfig


def load_config(path: str | Path) -> ResearchConfig:
    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    repos = [_load_repo_config(item) for item in data.get("repos", [])]
    if not repos:
        raise ValueError(f"No repositories configured in {config_path}")
    return ResearchConfig(
        repos=repos,
        mirrors_dir=data.get("mirrors_dir", "research/mirrors"),
        artifacts_dir=data.get("artifacts_dir", "research/artifacts"),
        reports_dir=data.get("reports_dir", "research/daily"),
    )


def _load_repo_config(data: dict) -> RepoConfig:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Each repo entry must include a non-empty name")
    return RepoConfig(
        name=name,
        repo_url=data.get("repo_url"),
        local_path=data.get("local_path"),
        default_branch=data.get("default_branch", "main"),
        category=data.get("category", "memory"),
        watch_paths=list(data.get("watch_paths", [])),
        signals=list(data.get("signals", ["commits", "prs", "releases", "changelog"])),
        notes=data.get("notes", ""),
        bootstrap_commits=int(data.get("bootstrap_commits", 20)),
    )
