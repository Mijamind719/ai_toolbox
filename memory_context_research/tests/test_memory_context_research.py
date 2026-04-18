from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from memory_context_research.config import load_config
from memory_context_research.main import run
from memory_context_research.models import RepoState
from memory_context_research.state import load_state, save_state


def test_load_config_applies_defaults(tmp_path):
    config_path = tmp_path / "repos.yaml"
    config_path.write_text(
        """
repos:
  - name: memory-lab
    local_path: /tmp/memory-lab
""".strip()
        + "\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.mirrors_dir == "research/mirrors"
    assert config.reports_dir == "research/daily"
    assert config.repos[0].default_branch == "main"
    assert config.repos[0].signals == ["commits", "prs", "releases", "changelog"]


def test_state_round_trip(tmp_path):
    state_path = tmp_path / "state.json"
    original = {
        "memory-lab": RepoState(
            last_commit="abc123",
            last_run_at="2026-04-18T00:00:00+00:00",
            last_success_at="2026-04-18T00:00:01+00:00",
        )
    }
    save_state(state_path, original)

    loaded = load_state(state_path)

    assert loaded["memory-lab"].last_commit == "abc123"
    assert loaded["memory-lab"].last_success_at == "2026-04-18T00:00:01+00:00"


def test_run_generates_report_and_state(tmp_path):
    repo_dir = tmp_path / "memory-repo"
    _init_git_repo(repo_dir)
    tracked_file = repo_dir / "src" / "memory" / "engine.py"
    tracked_file.parent.mkdir(parents=True, exist_ok=True)
    tracked_file.write_text("def recall():\n    return 'v1'\n", encoding="utf-8")
    _git(repo_dir, "add", ".")
    _git(repo_dir, "commit", "-m", "add memory retrieval engine")

    config_path = tmp_path / "repos.yaml"
    state_path = tmp_path / "state.json"
    reports_dir = tmp_path / "reports"
    artifacts_dir = tmp_path / "artifacts"
    config_path.write_text(
        f"""
reports_dir: {reports_dir}
artifacts_dir: {artifacts_dir}
repos:
  - name: memory-repo
    local_path: {repo_dir}
    default_branch: main
    watch_paths:
      - src/memory
    notes: 关注召回与记忆建模
""".strip()
        + "\n",
        encoding="utf-8",
    )

    report_path = run(str(config_path), str(state_path), "2026-04-18")
    report_body = report_path.read_text(encoding="utf-8")
    state = load_state(state_path)
    summary = json.loads(
        (artifacts_dir / "2026-04-18" / "memory-repo" / "summary.json").read_text(
            encoding="utf-8"
        )
    )

    assert "## memory-repo" in report_body
    assert "检索 / 召回" in report_body or "memory" in report_body
    assert state["memory-repo"].last_commit
    assert summary["status"] == "ok"


def _init_git_repo(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    _git(repo_dir, "init", "-b", "main")
    _git(repo_dir, "config", "user.name", "Memory Context Research Test")
    _git(repo_dir, "config", "user.email", "memory-context-research@example.com")


def _git(repo_dir: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        check=True,
        capture_output=True,
        text=True,
    )
