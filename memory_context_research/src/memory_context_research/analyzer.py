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
from memory_context_research.models import CommitInfo, RepoAnalysis, RepoConfig, RepoState

FEATURE_HINTS = (
    "feat",
    "add",
    "introduc",
    "support",
    "enable",
    "implement",
)
IMPROVEMENT_HINTS = (
    "fix",
    "improve",
    "harden",
    "stabil",
    "optimiz",
    "migrate",
)
NOISE_HINTS = (
    "docs",
    "doc:",
    "test",
    "chore",
    "release",
    "version",
    "bump",
    "changelog",
    "merge pull request",
    "merge remote-tracking",
    "security alerts",
    "remove conductor.json shim",
)
THEME_RULES = (
    (
        "worktree_scope",
        "工作树上下文归并 / 作用域隔离",
        ("worktree", "project", "remap", "adopt", "merged", "observation"),
    ),
    ("retrieval", "检索 / 召回", ("retriev", "search", "rerank", "chroma", "vector", "embed")),
    ("session_memory", "记忆存储 / 会话归档", ("memory", "session", "sqlite", "store", "timeline", "archive")),
    ("context_injection", "上下文组织 / 注入", ("context", "prompt", "window", "compiler", "builder")),
    ("agent_integration", "Agent / MCP 集成", ("mcp", "plugin", "agent", "skill", "worker")),
)


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
        "commits": [
            {"sha": commit.sha, "subject": commit.subject, "files": commit.files} for commit in commits
        ],
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

    scored_commits = score_commits(commits, repo.watch_paths)
    signal_commits = [item for item in scored_commits if item["score"] >= 5]
    improvement_commits = [item for item in scored_commits if 2 <= item["score"] < 5]
    selected_items = (signal_commits or improvement_commits)[:3]
    selected_commits = [item["commit"] for item in selected_items]
    theme_key, theme_label = infer_theme(selected_commits, matched_files)
    status = "ok" if signal_commits else "maintenance"
    evidence["signal_commits"] = [
        {"sha": item["commit"].sha, "subject": item["commit"].subject, "score": item["score"]}
        for item in selected_items
    ]
    evidence["signal_commit_count"] = len(signal_commits)
    evidence["improvement_commit_count"] = len(improvement_commits)

    return (
        RepoAnalysis(
            repo=repo.name,
            status=status,
            conclusion=build_capability_summary(status, theme_label, selected_commits, matched_files),
            new_capabilities=[commit.subject for commit in selected_commits],
            why_it_matters=build_why_it_matters(
                status=status,
                signal_count=len(signal_commits),
                improvement_count=len(improvement_commits),
                matched_file_count=len(matched_files),
                theme_label=theme_label,
            ),
            ov_value=build_ov_value(
                theme_key=theme_key,
                layers=infer_ov_layers(matched_files, selected_commits),
                notes=repo.notes,
            ),
            evidence=evidence,
            confidence=infer_confidence(status, len(signal_commits), len(improvement_commits)),
        ),
        current_head,
    )


def build_capability_summary(
    status: str,
    theme_label: str,
    commits: list[CommitInfo],
    matched_files: list[str],
) -> str:
    if status == "ok":
        if len(commits) >= 2:
            return f"这轮核心增量聚焦{theme_label}，而且是连续功能性推进，值得重点跟踪。"
        return f"这轮出现了明确的{theme_label}功能信号，值得继续观察其后续实现。"
    if commits:
        return f"这轮增量以{theme_label}相关强化和修复为主，暂未看到足够明确的新功能发布。"
    if any("memory" in path.lower() for path in matched_files):
        return "这轮增量触达了 memory 相关代码，但目前更像维护性更新，暂未看到明确新增能力。"
    return "这轮增量触达了目标领域代码，但目前更像维护性更新，暂未看到明确新增能力。"


def infer_ov_layers(matched_files: list[str], commits: list[CommitInfo]) -> list[str]:
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


def score_commits(commits: list[CommitInfo], watch_paths: list[str]) -> list[dict[str, object]]:
    scored: list[dict[str, object]] = []
    normalized_watch_paths = [path.rstrip("/") + "/" for path in watch_paths if path]
    for commit in commits:
        subject = commit.subject.lower()
        score = 0

        if any(subject.startswith(prefix) for prefix in ("feat", "add", "support", "introduce")):
            score += 6
        if any(hint in subject for hint in FEATURE_HINTS):
            score += 3
        if any(hint in subject for hint in IMPROVEMENT_HINTS):
            score += 2
        if any(hint in subject for hint in NOISE_HINTS):
            score -= 4
        if subject.startswith("merge pull request"):
            score -= 3

        score += score_commit_files(commit.files, normalized_watch_paths)
        scored.append({"commit": commit, "score": score})

    scored.sort(key=lambda item: (int(item["score"]), str(item["commit"].subject)), reverse=True)
    return scored


def score_commit_files(files: list[str], watch_paths: list[str]) -> int:
    score = 0
    for file_path in files:
        lowered = file_path.lower()
        if watch_paths and any(file_path.startswith(prefix) for prefix in watch_paths):
            score += 1
        if any(
            keyword in lowered
            for keyword in (
                "memory",
                "context",
                "session",
                "search",
                "retriev",
                "mcp",
                "plugin",
                "worker",
                "store",
                "observation",
                "project",
                "worktree",
            )
        ):
            score += 1
    return min(score, 4)


def infer_theme(commits: list[CommitInfo], matched_files: list[str]) -> tuple[str, str]:
    joined = " ".join(matched_files + [commit.subject for commit in commits]).lower()
    best_key = "general"
    best_label = "上下文 / 记忆系统"
    best_score = -1
    for key, label, keywords in THEME_RULES:
        score = sum(joined.count(keyword) for keyword in keywords)
        if score > best_score:
            best_key = key
            best_label = label
            best_score = score
    return best_key, best_label


def build_why_it_matters(
    status: str,
    signal_count: int,
    improvement_count: int,
    matched_file_count: int,
    theme_label: str,
) -> list[str]:
    if status == "ok":
        return [
            f"这轮有 {signal_count} 个高信号 commit 指向{theme_label}，不是单纯的发布或文档噪音。",
            f"相关改动覆盖 {matched_file_count} 个目标文件，说明这条方向已经进入实现层而非停留在说明层。",
        ]
    return [
        f"虽然命中了 {matched_file_count} 个目标文件，但高信号功能 commit 不足，当前更像维护性迭代。",
        f"仍有 {improvement_count} 个改进型 commit 触达{theme_label}，适合继续观察是否会在后续演化成明确功能。",
    ]


def build_ov_value(theme_key: str, layers: list[str], notes: str) -> list[str]:
    theme_guidance = {
        "worktree_scope": "重点看 OV 如何处理多 worktree / 多项目上下文隔离与归并。",
        "retrieval": "重点看 OV 的检索召回、重排和上下文命中质量是否有可借鉴空间。",
        "session_memory": "重点看 OV 的 session 存储、归档与记忆更新策略。",
        "context_injection": "重点看 OV 的上下文组织、压缩和注入链路。",
        "agent_integration": "重点看 OV 的 MCP / plugin / agent 侧集成方式。",
    }
    values = [
        theme_guidance.get(
            theme_key,
            "重点看这些变化是否会沉淀成 OV 可复用的上下文 / 记忆能力。",
        )
    ]
    values.extend([f"建议优先关注 {layer}。" for layer in layers])
    if notes:
        values.append(f"仓库备注：{notes}")
    return values


def infer_confidence(status: str, signal_count: int, improvement_count: int) -> str:
    if status == "ok" and signal_count >= 2:
        return "high"
    if status == "ok" or improvement_count > 0:
        return "medium"
    return "low"
