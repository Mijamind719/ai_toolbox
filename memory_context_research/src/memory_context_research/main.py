from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory_context_research.analyzer import analyze_repo
from memory_context_research.config import load_config
from memory_context_research.models import RepoAnalysis, RepoState
from memory_context_research.report import write_artifacts, write_daily_report
from memory_context_research.state import load_state, save_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily memory context research MVP")
    parser.add_argument("--config", required=True, help="Path to repos.yaml")
    parser.add_argument(
        "--state",
        default="config/state.json",
        help="Path to persistent state JSON",
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Report date in YYYY-MM-DD format",
    )
    return parser


def run(config_path: str, state_path: str, report_date: str) -> Path:
    config = load_config(config_path)
    state = load_state(state_path)
    analyses: list[RepoAnalysis] = []
    run_at = datetime.now(timezone.utc).isoformat()

    for repo in config.repos:
        repo_state = state.get(repo.name, RepoState())
        state[repo.name] = repo_state
        repo_state.last_run_at = run_at
        try:
            analysis, current_head = analyze_repo(repo, repo_state, config.mirrors_dir)
        except Exception as exc:  # pragma: no cover
            analysis = RepoAnalysis(
                repo=repo.name,
                status="error",
                conclusion="今天的分析失败，建议检查仓库访问和 git 状态。",
                evidence={},
                confidence="low",
                error=str(exc),
            )
            analyses.append(analysis)
            write_artifacts(config.artifacts_dir, report_date, analysis)
            continue

        analyses.append(analysis)
        write_artifacts(config.artifacts_dir, report_date, analysis)
        repo_state.last_commit = current_head
        repo_state.last_success_at = run_at

    report_path = write_daily_report(config.reports_dir, report_date, analyses)
    save_state(state_path, state)
    return report_path


def main() -> int:
    args = build_parser().parse_args()
    report_path = run(args.config, args.state, args.date)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
