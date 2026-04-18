from __future__ import annotations

from pathlib import Path

from memory_context_research.git_tools import (
    determine_base_commit,
    fetch_repo,
    head_commit,
    list_changed_files,
    list_commits_since,
    prepare_repo,
    relevant_files,
)
from memory_context_research.models import RepoAnalysis, RepoConfig, RepoState


def analyze_repo(
    repo: RepoConfig,
    repo_state: RepoState,
    mirrors_dir: str | Path,
) -> tuple[RepoAnalysis, str]:
    repo_path = prepare_repo(repo, mirrors_dir)
    fetch_repo(repo_path, repo.default_branch)

    current_head = head_commit(repo_path)
    base_commit = determine_base_commit(repo_path, repo_state.last_commit, repo.bootstrap_commits)
    commits = list_commits_since(repo_path, base_commit)
    changed_files = list_changed_files(repo_path, base_commit)
    matched_files = relevant_files(changed_files, repo.watch_paths)

    evidence = {
        "repo_path": str(repo_path),
        "base_commit": base_commit,
        "head_commit": current_head,
        "commit_count": len(commits),
        "changed_files": changed_files,
        "matched_files": matched_files,
        "commits": [{"sha": commit.sha, "subject": commit.subject} for commit in commits],
    }

    if not commits:
        return (
            RepoAnalysis(
                repo=repo.name,
                status="no_change",
                conclusion="今天没有新的 commit，暂无需要跟进的变化。",
                evidence=evidence,
                confidence="high",
            ),
            current_head,
        )

    if not matched_files:
        return (
            RepoAnalysis(
                repo=repo.name,
                status="no_relevant_change",
                conclusion="今天有增量更新，但没有发现值得跟进的上下文 / 记忆能力变化。",
                evidence=evidence,
                confidence="medium",
            ),
            current_head,
        )

    layers = infer_ov_layers(matched_files, commits)
    summary_commits = [commit.subject for commit in commits[-3:]]
    capability_text = build_capability_summary(matched_files, commits)
    why_it_matters = [
        f"相关变更覆盖 {len(matched_files)} 个文件，说明这不是单点注释级改动。",
        f"最近增量里有 {len(commits)} 个 commit 涉及目标领域关键词或重点目录。",
    ]
    ov_value = [f"建议优先关注 {layer}。" for layer in layers]
    if repo.notes:
        ov_value.append(f"仓库备注：{repo.notes}")

    return (
        RepoAnalysis(
            repo=repo.name,
            status="ok",
            conclusion=capability_text,
            new_capabilities=summary_commits,
            why_it_matters=why_it_matters,
            ov_value=ov_value,
            evidence=evidence,
            confidence="medium",
        ),
        current_head,
    )


def build_capability_summary(matched_files: list[str], commits) -> str:
    if any("retriev" in path.lower() or "search" in path.lower() for path in matched_files):
        return "新增变化主要集中在检索 / 召回相关能力，值得关注其对上下文命中质量的影响。"
    if any("session" in path.lower() or "context" in path.lower() for path in matched_files):
        return "新增变化主要集中在 session / context 管理能力，可能影响上下文组织与压缩方式。"
    if any("memory" in path.lower() for path in matched_files):
        return "新增变化主要集中在 memory 相关能力，值得关注其建模、抽取或更新策略。"
    latest_subject = commits[-1].subject if commits else "最近一次提交"
    return f"最新增量显示该仓库在目标领域持续演进，当前可先从“{latest_subject}”切入进一步观察。"


def infer_ov_layers(matched_files: list[str], commits) -> list[str]:
    joined = " ".join(matched_files + [commit.subject for commit in commits]).lower()
    layers: list[str] = []
    if "retriev" in joined or "search" in joined or "rerank" in joined:
        layers.append("OV 的 retrieval 层")
    if "session" in joined or "context" in joined or "window" in joined:
        layers.append("OV 的 session / context 层")
    if "memory" in joined or "schema" in joined or "extract" in joined or "merge" in joined:
        layers.append("OV 的 memory schema / extraction 层")
    if "prompt" in joined or "mcp" in joined or "skill" in joined or "agent" in joined:
        layers.append("OV 的 agent integration 层")
    return layers or ["OV 的研究观察层"]
