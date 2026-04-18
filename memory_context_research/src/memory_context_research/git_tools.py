from __future__ import annotations

import subprocess
from pathlib import Path

from memory_context_research.models import CommitInfo, RepoConfig

NOISE_PATH_MARKERS = (
    ".github/",
    "docs/",
    "doc/",
    "tests/",
    "test/",
)


def prepare_repo(repo: RepoConfig, mirrors_dir: str | Path) -> Path:
    if repo.local_path:
        return Path(repo.local_path).resolve()

    if not repo.repo_url:
        raise ValueError(f"Repo {repo.name} must define repo_url or local_path")

    repo_path = Path(mirrors_dir).resolve() / repo.name
    if repo_path.exists():
        return repo_path

    repo_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--filter=blob:none", "--branch", repo.default_branch, repo.repo_url, str(repo_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return repo_path


def fetch_repo(repo_path: str | Path, branch: str) -> None:
    remotes = _git_lines(repo_path, "remote")
    if "origin" not in remotes:
        return
    subprocess.run(
        ["git", "-C", str(repo_path), "fetch", "origin", branch, "--prune"],
        check=True,
        capture_output=True,
        text=True,
    )


def head_commit(repo_path: str | Path) -> str:
    return _git(repo_path, "rev-parse", "HEAD")


def commit_exists(repo_path: str | Path, commit: str | None) -> bool:
    if not commit:
        return False
    result = subprocess.run(
        ["git", "-C", str(repo_path), "cat-file", "-e", f"{commit}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def determine_base_commit(
    repo_path: str | Path,
    previous_commit: str | None,
    bootstrap_commits: int,
) -> str | None:
    if commit_exists(repo_path, previous_commit):
        return previous_commit

    revisions = _git_lines(
        repo_path,
        "rev-list",
        "--max-count",
        str(max(bootstrap_commits, 1) + 1),
        "HEAD",
    )
    if len(revisions) <= 1:
        return None
    return revisions[-1]


def list_commits_since(repo_path: str | Path, base_commit: str | None) -> list[CommitInfo]:
    if base_commit:
        lines = _git_lines(repo_path, "log", "--format=%H%x1f%s", f"{base_commit}..HEAD")
    else:
        lines = _git_lines(repo_path, "log", "--format=%H%x1f%s", "--max-count", "1", "HEAD")

    commits: list[CommitInfo] = []
    for line in lines:
        sha, subject = line.split("\x1f", maxsplit=1)
        commits.append(CommitInfo(sha=sha, subject=subject))
    commits.reverse()
    return commits


def list_changed_files(repo_path: str | Path, base_commit: str | None) -> list[str]:
    if base_commit:
        files = _git_lines(repo_path, "diff", "--name-only", f"{base_commit}..HEAD")
    else:
        files = _git_lines(repo_path, "show", "--pretty=format:", "--name-only", "HEAD")
    return [item for item in files if item]


def relevant_files(files: list[str], watch_paths: list[str]) -> list[str]:
    if not files:
        return []

    normalized_watch_paths = [path.rstrip("/") + "/" for path in watch_paths if path]
    relevant: list[str] = []
    for file_path in files:
        lowered = file_path.lower()
        if any(marker in lowered for marker in NOISE_PATH_MARKERS):
            continue
        if normalized_watch_paths and any(
            file_path.startswith(prefix) for prefix in normalized_watch_paths
        ):
            relevant.append(file_path)
            continue
        if _contains_research_keyword(lowered):
            relevant.append(file_path)
    return relevant


def _contains_research_keyword(value: str) -> bool:
    keywords = (
        "memory",
        "context",
        "session",
        "retriev",
        "recall",
        "prompt",
        "rag",
        "search",
        "mcp",
        "skill",
    )
    return any(keyword in value for keyword in keywords)


def _git(repo_path: str | Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_lines(repo_path: str | Path, *args: str) -> list[str]:
    output = _git(repo_path, *args)
    return [line for line in output.splitlines() if line]
