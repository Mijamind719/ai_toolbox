from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RepoConfig:
    name: str
    repo_url: str | None = None
    local_path: str | None = None
    default_branch: str = "main"
    category: str = "memory"
    watch_paths: list[str] = field(default_factory=list)
    signals: list[str] = field(
        default_factory=lambda: ["commits", "prs", "releases", "changelog"]
    )
    notes: str = ""
    bootstrap_commits: int = 20


@dataclass
class ResearchConfig:
    repos: list[RepoConfig]
    mirrors_dir: str = "research/mirrors"
    artifacts_dir: str = "research/artifacts"
    reports_dir: str = "research/daily"


@dataclass
class RepoState:
    last_commit: str | None = None
    last_run_at: str | None = None
    last_success_at: str | None = None


@dataclass
class CommitInfo:
    sha: str
    subject: str
    files: list[str] = field(default_factory=list)


@dataclass
class RepoAnalysis:
    repo: str
    status: str
    conclusion: str
    new_capabilities: list[str] = field(default_factory=list)
    why_it_matters: list[str] = field(default_factory=list)
    ov_value: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: str = "low"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
