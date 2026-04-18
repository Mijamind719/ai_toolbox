from __future__ import annotations

import json
from pathlib import Path

from memory_context_research.models import RepoAnalysis


def write_artifacts(
    artifacts_dir: str | Path,
    report_date: str,
    analysis: RepoAnalysis,
) -> None:
    target_dir = Path(artifacts_dir) / report_date / analysis.repo
    target_dir.mkdir(parents=True, exist_ok=True)
    raw_path = target_dir / "raw.json"
    summary_path = target_dir / "summary.json"
    payload = analysis.to_dict()
    raw_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {
        "repo": analysis.repo,
        "status": analysis.status,
        "conclusion": analysis.conclusion,
        "confidence": analysis.confidence,
        "new_capabilities": analysis.new_capabilities,
        "ov_value": analysis.ov_value,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_daily_report(
    reports_dir: str | Path,
    report_date: str,
    analyses: list[RepoAnalysis],
) -> Path:
    report_path = Path(reports_dir) / f"{report_date}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_daily_report(report_date, analyses), encoding="utf-8")
    return report_path


def render_daily_report(report_date: str, analyses: list[RepoAnalysis]) -> str:
    lines = [
        "# Context / Memory Repo Daily",
        f"Date: {report_date}",
        "",
    ]
    for analysis in analyses:
        lines.extend(render_repo_section(analysis))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_repo_section(analysis: RepoAnalysis) -> list[str]:
    lines = [
        f"## {analysis.repo}",
        f"结论：{analysis.conclusion}",
    ]

    if analysis.status not in {"ok"}:
        evidence = analysis.evidence or {}
        if evidence.get("head_commit"):
            lines.append(f"证据：head={evidence['head_commit']}")
        return lines

    if analysis.new_capabilities:
        lines.append("")
        lines.append("新增功能：")
        lines.extend([f"- {item}" for item in analysis.new_capabilities])

    if analysis.why_it_matters:
        lines.append("")
        lines.append("为什么重要：")
        lines.extend([f"- {item}" for item in analysis.why_it_matters])

    if analysis.ov_value:
        lines.append("")
        lines.append("对 OV 的潜在价值：")
        lines.extend([f"- {item}" for item in analysis.ov_value])

    evidence = analysis.evidence or {}
    lines.append("")
    lines.append("证据：")
    lines.append(
        f"- commit range: {evidence.get('base_commit') or 'bootstrap'} -> {evidence.get('head_commit', 'unknown')}"
    )
    lines.append(f"- 相关文件数：{len(evidence.get('matched_files', []))}")
    if evidence.get("commits"):
        lines.append(
            "- 相关 commits: "
            + ", ".join(
                f"{item['sha'][:8]} {item['subject']}" for item in evidence["commits"][-3:]
            )
        )
    lines.append(f"- 置信度：{analysis.confidence}")
    return lines
