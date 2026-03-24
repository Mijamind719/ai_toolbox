"""Engine-specific diagnostics adapters for capture traces."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from tools.context_capture.storage import JsonlStore


LCM_STAGE_LABELS = {
    "bootstrap_entry": "Bootstrap 开始",
    "bootstrap_import": "Bootstrap 导入",
    "bootstrap_result": "Bootstrap 结果",
    "afterTurn_entry": "afterTurn 回调",
    "ingest": "消息持久化",
    "assemble_skip": "Assemble 跳过",
    "leaf_pass_detail": "叶子压缩详情",
    "compact_skip": "压缩跳过",
    "compact_phase": "压缩阶段",
    "compact_result": "压缩结果",
    "assemble_input": "原始消息输入",
    "compaction_evaluate": "压缩决策",
    "leaf_summary": "叶子摘要",
    "dag_aggregate": "DAG 聚合摘要",
    "context_assemble": "上下文组装",
    "assemble_output": "最终输出",
}

LCM_PRE_HTTP_STAGES = {
    "bootstrap_entry",
    "bootstrap_import",
    "bootstrap_result",
    "assemble_skip",
    "assemble_input",
    "context_assemble",
    "assemble_output",
}

LCM_SECTION_SPECS = (
    ("bootstrap", "summary", "Bootstrap", {"bootstrap_entry", "bootstrap_import", "bootstrap_result"}),
    (
        "assemble",
        "assemble",
        "Context Assemble",
        {
            "assemble_skip",
            "assemble_input",
            "compaction_evaluate",
            "leaf_pass_detail",
            "leaf_summary",
            "dag_aggregate",
            "context_assemble",
            "assemble_output",
            "compact_skip",
            "compact_phase",
            "compact_result",
        },
    ),
    ("capture", "capture", "afterTurn", {"afterTurn_entry"}),
    ("ingest", "ingest", "Ingest", {"ingest"}),
)

OPENVIKING_INJECT_DETAIL_RE = re.compile(r"openviking:\s+inject-detail\s+(?P<json>\{.*\})")
OPENVIKING_CAPTURE_DETAIL_RE = re.compile(r"openviking:\s+capture-detail\s+(?P<json>\{.*\})")
OPENVIKING_CAPTURE_CHECK_RE = re.compile(
    r"openviking:\s+capture-check\s+shouldCapture=(?P<should>\w+)\s+reason=(?P<reason>[^ ]+)\s+newMsgCount=(?P<count>\d+)\s+text=\"(?P<text>.*)\""
)
OPENVIKING_SWITCH_RE = re.compile(
    r"openviking:\s+switched to agentId=(?P<agent>[^ ]+)\s+for\s+(?P<phase>[^ ]+)"
)
OPENVIKING_INJECT_COUNT_RE = re.compile(r"openviking:\s+injecting\s+(?P<count>\d+)\s+memories into context")
OPENVIKING_AUTOCAPTURE_RE = re.compile(
    r"openviking:\s+auto-captured\s+(?P<captured>\d+)\s+new messages,\s+extracted\s+(?P<extracted>\d+)\s+memories"
)


def _parse_ts_millis(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if not isinstance(value, str) or not value:
        return None

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _ts_in_window(ts: Any, start_ts: int, end_ts: int, *, pre_ms: int, post_ms: int) -> bool:
    return isinstance(ts, int) and (start_ts - pre_ms) <= ts <= (end_ts + post_ms)


def _trace_window(trace: dict[str, Any]) -> tuple[int | None, int | None]:
    events = trace.get("events", [])
    if not isinstance(events, list) or not events:
        return None, None
    start_ts = getattr(events[0], "ts", None)
    end_ts = getattr(events[-1], "ts", None)
    return start_ts if isinstance(start_ts, int) else None, end_ts if isinstance(end_ts, int) else None


def _safe_json_loads(text: Any) -> dict[str, Any] | list[Any] | None:
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, (dict, list)):
        return parsed
    return None


def _compact_json(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except TypeError:
        return str(value)


def _preview_text(value: Any, *, max_length: int = 160) -> str:
    if isinstance(value, str):
        text = value.strip()
    else:
        text = _compact_json(value).strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _get_lcm_path() -> Path:
    configured = os.environ.get("LCM_DIAGNOSTICS_PATH", "").strip()
    if configured:
        return Path(os.path.expanduser(configured))
    return Path.home() / ".openclaw" / "lcm-diagnostics.jsonl"


def _gateway_log_path(data_dir: Path) -> Path | None:
    configured = os.environ.get("CONTEXT_CAPTURE_GATEWAY_LOG_PATH", "").strip()
    if configured:
        path = Path(configured)
        return path if path.exists() else None

    local = data_dir / "gateway.log.jsonl"
    return local if local.exists() else None


def _load_lcm_entries() -> list[dict[str, Any]]:
    path = _get_lcm_path()
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    try:
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            parsed = _safe_json_loads(raw_line)
            if isinstance(parsed, dict):
                entries.append(parsed)
    except OSError:
        return []
    return entries


def _load_gateway_records(data_dir: Path) -> list[dict[str, Any]]:
    path = _gateway_log_path(data_dir)
    if path is None:
        return []

    records: list[dict[str, Any]] = []
    try:
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            parsed = _safe_json_loads(raw_line)
            if not isinstance(parsed, dict):
                continue
            ts = _parse_ts_millis(parsed.get("time"))
            message = parsed.get("1")
            if ts is None or not isinstance(message, str) or not message:
                continue
            records.append({"ts": ts, "message": message, "raw": parsed})
    except OSError:
        return []
    return records


def _load_http_flows(data_dir: Path) -> list[dict[str, Any]]:
    store = JsonlStore(data_dir / "raw.jsonl")
    grouped: dict[str, dict[str, Any]] = {}
    anon_counter = 0
    for raw in store.read_all() or []:
        if raw.get("channel") != "http":
            continue
        flow_id = raw.get("flow_id")
        if not isinstance(flow_id, str) or not flow_id:
            anon_counter += 1
            flow_id = f"anon:{anon_counter}"
        bucket = grouped.setdefault(flow_id, {"flow_id": flow_id, "request": None, "response": None})
        if raw.get("direction") == "request":
            bucket["request"] = raw
        elif raw.get("direction") == "response":
            bucket["response"] = raw
    return list(grouped.values())


def load_diagnostics_context(data_dir: Path) -> dict[str, Any]:
    return {
        "lcm_entries": _load_lcm_entries(),
        "gateway_records": _load_gateway_records(data_dir),
        "http_flows": _load_http_flows(data_dir),
    }


def _extract_text_from_content(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            text = _extract_text_from_content(item)
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
    if isinstance(value, dict):
        text_value = value.get("text")
        if isinstance(text_value, str) and text_value.strip():
            return text_value.strip()
        return _extract_text_from_content(value.get("content"))
    return ""


def extract_trace_preview(trace: dict[str, Any], *, max_length: int = 120) -> str:
    events = trace.get("events", [])
    for event in events:
        payload = getattr(event, "payload_full", None)
        if not isinstance(payload, dict):
            continue
        if getattr(event, "direction", None) == "user->gateway":
            candidate = _extract_text_from_content(payload.get("text") or payload.get("message") or payload.get("content"))
            if candidate:
                return _preview_text(candidate, max_length=max_length)
        if getattr(event, "direction", None) == "gateway->model":
            messages = payload.get("messages")
            if isinstance(messages, list):
                for message in reversed(messages):
                    if not isinstance(message, dict) or message.get("role") != "user":
                        continue
                    candidate = _extract_text_from_content(message.get("content"))
                    if candidate:
                        return _preview_text(candidate, max_length=max_length)
            direct_input = payload.get("input")
            if isinstance(direct_input, str) and direct_input.strip():
                return _preview_text(direct_input, max_length=max_length)
    return ""


def _matching_lcm_entries(
    trace: dict[str, Any],
    *,
    lcm_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    start_ts, end_ts = _trace_window(trace)
    if start_ts is None or end_ts is None:
        return []

    matched: list[dict[str, Any]] = []
    for entry in lcm_entries:
        ts = entry.get("ts")
        if not isinstance(ts, (int, float)):
            continue
        stage = entry.get("stage")
        pre_ms = 10_000 if stage in LCM_PRE_HTTP_STAGES else 5_000
        post_ms = 5_000 if stage in LCM_PRE_HTTP_STAGES else 15_000
        if _ts_in_window(int(ts), start_ts, end_ts, pre_ms=pre_ms, post_ms=post_ms):
            matched.append(entry)
    return sorted(matched, key=lambda item: int(item.get("ts", 0)))


def _matching_openviking_records(
    trace: dict[str, Any],
    *,
    gateway_records: list[dict[str, Any]],
    http_flows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    start_ts, end_ts = _trace_window(trace)
    if start_ts is None or end_ts is None:
        return [], []

    matched_logs = [
        record
        for record in gateway_records
        if "openviking:" in record["message"]
        and _ts_in_window(record["ts"], start_ts, end_ts, pre_ms=12_000, post_ms=20_000)
    ]

    matched_flows: list[dict[str, Any]] = []
    for flow in http_flows:
        request = flow.get("request")
        response = flow.get("response")
        request_url = request.get("url") if isinstance(request, dict) else None
        response_url = response.get("url") if isinstance(response, dict) else None
        url = request_url if isinstance(request_url, str) and request_url else response_url
        if not isinstance(url, str) or not _is_openviking_url(url):
            continue

        request_ts = request.get("ts") if isinstance(request, dict) else None
        response_ts = response.get("ts") if isinstance(response, dict) else None
        ts = request_ts if isinstance(request_ts, int) else response_ts
        if not isinstance(ts, int):
            continue
        if _ts_in_window(ts, start_ts, end_ts, pre_ms=12_000, post_ms=20_000):
            matched_flows.append(flow)

    matched_logs.sort(key=lambda item: item["ts"])
    matched_flows.sort(
        key=lambda item: (
            item.get("request", {}).get("ts")
            if isinstance(item.get("request"), dict) and isinstance(item["request"].get("ts"), int)
            else item.get("response", {}).get("ts", 0)
        )
    )
    return matched_logs, matched_flows


def _is_openviking_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port
    path = parsed.path or ""
    if port == 1933:
        return True
    if host in {"127.0.0.1", "localhost"} and path.startswith("/api/v1/"):
        return True
    return False


def _stage_label(stage: str) -> str:
    return LCM_STAGE_LABELS.get(stage, stage)


def _item(label: str, value: Any, *, tone: str | None = None) -> dict[str, Any]:
    item = {"label": label, "value": "" if value is None else str(value)}
    if tone:
        item["tone"] = tone
    return item


def _stat(label: str, value: Any) -> dict[str, Any]:
    return {"label": label, "value": "" if value is None else str(value)}


def _raw_ref(label: str, value: Any) -> dict[str, Any]:
    return {"label": label, "value": _compact_json(value)}


def _build_lossless_sections(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for section_id, kind, title, stages in LCM_SECTION_SPECS:
        section_entries = [entry for entry in entries if entry.get("stage") in stages]
        if not section_entries:
            continue

        stats: list[dict[str, Any]] = [_stat("诊断条目", len(section_entries))]
        items: list[dict[str, Any]] = []
        raw_refs: list[dict[str, Any]] = []

        if section_id == "ingest":
            total_tokens = sum(
                int((entry.get("data") or {}).get("tokenCount") or 0) for entry in section_entries
            )
            stats.append(_stat("消息数", len(section_entries)))
            stats.append(_stat("tokens", total_tokens))
            for entry in section_entries:
                data = entry.get("data") or {}
                role = data.get("role") or "?"
                seq = data.get("seq")
                preview = data.get("contentPreview") or "(empty)"
                items.append(_item(f"{role} seq={seq}", preview))
        else:
            for entry in section_entries:
                data = entry.get("data") or {}
                stage = str(entry.get("stage") or "")
                if stage == "afterTurn_entry":
                    items.append(
                        _item(
                            _stage_label(stage),
                            f"总消息={data.get('totalMessages') or 0}, 新消息={data.get('newMessageCount') or 0}, prePrompt={data.get('prePromptMessageCount') or 0}",
                        )
                    )
                elif stage == "assemble_output":
                    items.append(
                        _item(
                            _stage_label(stage),
                            f"输出消息={data.get('outputMessagesCount') or 0}, 估算tokens={data.get('estimatedTokens') or 0}, 节省={data.get('tokensSaved') or 0}",
                        )
                    )
                    if data.get("tokensSaved"):
                        stats.append(_stat("节省 tokens", data.get("tokensSaved")))
                elif stage == "context_assemble":
                    items.append(
                        _item(
                            _stage_label(stage),
                            f"summary={data.get('summaryCount') or 0}, raw={data.get('rawMessageCount') or 0}, freshTail={data.get('freshTailCount') or 0}",
                        )
                    )
                elif stage == "compaction_evaluate":
                    items.append(
                        _item(
                            _stage_label(stage),
                            f"当前tokens={data.get('currentTokens') or 0}, 预算={data.get('tokenBudget') or 0}, 需要压缩={bool(data.get('shouldCompact'))}",
                        )
                    )
                elif stage == "leaf_pass_detail":
                    items.append(
                        _item(
                            _stage_label(stage),
                            f"输入={data.get('inputTokens') or 0}, 输出={data.get('outputTokens') or 0}, 级别={data.get('level') or '-'}",
                        )
                    )
                elif stage == "compact_result":
                    items.append(
                        _item(
                            _stage_label(stage),
                            f"compacted={bool(data.get('compacted'))}, reason={data.get('reason') or '-'}",
                            tone="warning" if not data.get("ok", True) else None,
                        )
                    )
                else:
                    items.append(_item(_stage_label(stage), _preview_text(data or entry)))

        for entry in section_entries[:6]:
            raw_refs.append(_raw_ref(_stage_label(str(entry.get("stage") or "")), entry))

        sections.append(
            {
                "kind": kind,
                "title": title,
                "started_at": section_entries[0].get("ts"),
                "ended_at": section_entries[-1].get("ts"),
                "stats": stats,
                "items": items,
                "raw_refs": raw_refs,
            }
        )
    return sections


def _parse_openviking_json_fragment(message: str, pattern: re.Pattern[str]) -> dict[str, Any] | None:
    match = pattern.search(message)
    if match is None:
        return None
    parsed = _safe_json_loads(match.group("json"))
    return parsed if isinstance(parsed, dict) else None


def _classify_openviking_log(message: str) -> str:
    if "before_prompt_build" in message or "injecting " in message or "inject-detail" in message:
        return "recall"
    if "capture-check" in message:
        return "capture"
    if "afterTurn" in message or "auto-captured" in message or "capture-detail" in message or "auto-capture" in message:
        return "ingest"
    return "warning"


def _flow_path(flow: dict[str, Any]) -> str:
    request = flow.get("request")
    response = flow.get("response")
    url = None
    if isinstance(request, dict):
        url = request.get("url")
    if not isinstance(url, str) and isinstance(response, dict):
        url = response.get("url")
    if not isinstance(url, str):
        return ""
    return urlparse(url).path or ""


def _flow_ts(flow: dict[str, Any]) -> int | None:
    request = flow.get("request")
    response = flow.get("response")
    if isinstance(request, dict) and isinstance(request.get("ts"), int):
        return request["ts"]
    if isinstance(response, dict) and isinstance(response.get("ts"), int):
        return response["ts"]
    return None


def _flow_summary_item(flow: dict[str, Any]) -> dict[str, Any] | None:
    path = _flow_path(flow)
    request = flow.get("request") if isinstance(flow.get("request"), dict) else {}
    response = flow.get("response") if isinstance(flow.get("response"), dict) else {}
    request_body = _safe_json_loads(request.get("body_text"))
    response_body = _safe_json_loads(response.get("body_text"))

    if path == "/api/v1/search/find":
        if not isinstance(request_body, dict):
            return _item("Recall 请求", "search/find")
        count = ""
        if isinstance(response_body, dict):
            result = response_body.get("result")
            if isinstance(result, dict):
                memories = result.get("memories")
                if isinstance(memories, list):
                    count = f", 命中={len(memories)}"
        return _item(
            "Recall 请求",
            f"query={request_body.get('query') or '-'}, target={request_body.get('target_uri') or '-'}{count}",
        )

    if path.endswith("/messages"):
        role = request_body.get("role") if isinstance(request_body, dict) else None
        content = request_body.get("content") if isinstance(request_body, dict) else None
        return _item("Session 写入", f"role={role or '-'} { _preview_text(content or '') }")

    if path.endswith("/extract") or "/extract" in path:
        count = ""
        if isinstance(response_body, dict):
            result = response_body.get("result")
            if isinstance(result, list):
                count = f"extracted={len(result)}"
        return _item("Memory Extract", count or "extract")

    if path == "/api/v1/sessions":
        status = response.get("status_code")
        return _item("Session 创建", f"status={status or '-'}")

    return None


def _build_openviking_sections(logs: list[dict[str, Any]], flows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped_logs: dict[str, list[dict[str, Any]]] = {"recall": [], "capture": [], "ingest": [], "warning": []}
    for record in logs:
        grouped_logs[_classify_openviking_log(record["message"])].append(record)

    sections: list[dict[str, Any]] = []

    recall_items: list[dict[str, Any]] = []
    recall_raw: list[dict[str, Any]] = []
    recall_stats: list[dict[str, Any]] = []
    inject_count = 0
    for record in grouped_logs["recall"]:
        message = record["message"]
        switch_match = OPENVIKING_SWITCH_RE.search(message)
        if switch_match is not None:
            recall_items.append(_item("Agent 切换", f"{switch_match.group('agent')} for {switch_match.group('phase')}"))
            continue
        inject_match = OPENVIKING_INJECT_COUNT_RE.search(message)
        if inject_match is not None:
            inject_count = int(inject_match.group("count"))
            recall_items.append(_item("Inject", f"注入 {inject_count} 条 memories"))
            continue
        inject_detail = _parse_openviking_json_fragment(message, OPENVIKING_INJECT_DETAIL_RE)
        if inject_detail is not None:
            recall_raw.append(_raw_ref("inject-detail", inject_detail))
            memories = inject_detail.get("memories")
            if isinstance(memories, list):
                recall_stats.append(_stat("注入明细", len(memories)))
            continue
        recall_items.append(_item("Gateway 日志", message.replace("openviking:", "", 1).strip()))

    for flow in flows:
        path = _flow_path(flow)
        if path == "/api/v1/search/find":
            item = _flow_summary_item(flow)
            if item is not None:
                recall_items.append(item)
            recall_raw.append(_raw_ref("search/find", flow))

    if recall_items or recall_raw:
        if inject_count:
            recall_stats.append(_stat("注入条数", inject_count))
        sections.append(
            {
                "kind": "recall",
                "title": "OpenViking Recall",
                "started_at": min([r["ts"] for r in grouped_logs["recall"]] + [t for t in [_flow_ts(f) for f in flows if _flow_path(f) == "/api/v1/search/find"] if isinstance(t, int)], default=None),
                "ended_at": max([r["ts"] for r in grouped_logs["recall"]] + [t for t in [_flow_ts(f) for f in flows if _flow_path(f) == "/api/v1/search/find"] if isinstance(t, int)], default=None),
                "stats": recall_stats or [_stat("日志条目", len(grouped_logs["recall"]))],
                "items": recall_items,
                "raw_refs": recall_raw,
            }
        )

    capture_items: list[dict[str, Any]] = []
    capture_raw: list[dict[str, Any]] = []
    capture_stats: list[dict[str, Any]] = []
    for record in grouped_logs["capture"]:
        message = record["message"]
        check_match = OPENVIKING_CAPTURE_CHECK_RE.search(message)
        if check_match is not None:
            should_capture = check_match.group("should")
            reason = check_match.group("reason")
            count = check_match.group("count")
            text = check_match.group("text")
            capture_items.append(
                _item(
                    "Capture Decision",
                    f"shouldCapture={should_capture}, reason={reason}, newMsgCount={count}, text={_preview_text(text)}",
                    tone="warning" if should_capture.lower() != "true" else None,
                )
            )
            capture_stats.append(_stat("新消息数", count))
            continue
        capture_items.append(_item("Gateway 日志", message.replace("openviking:", "", 1).strip()))

    for record in grouped_logs["ingest"]:
        message = record["message"]
        auto_match = OPENVIKING_AUTOCAPTURE_RE.search(message)
        if auto_match is not None:
            capture_items.append(
                _item(
                    "Auto Capture",
                    f"captured={auto_match.group('captured')}, extracted={auto_match.group('extracted')}",
                )
            )
            capture_stats.append(_stat("提取 memories", auto_match.group("extracted")))
            continue
        capture_detail = _parse_openviking_json_fragment(message, OPENVIKING_CAPTURE_DETAIL_RE)
        if capture_detail is not None:
            capture_raw.append(_raw_ref("capture-detail", capture_detail))
            continue
        tone = "warning" if "failed" in message or "0 memories" in message else None
        capture_items.append(_item("Capture 日志", message.replace("openviking:", "", 1).strip(), tone=tone))

    for flow in flows:
        path = _flow_path(flow)
        if path == "/api/v1/search/find":
            continue
        item = _flow_summary_item(flow)
        if item is not None:
            capture_items.append(item)
            capture_raw.append(_raw_ref(path or "http", flow))

    if capture_items or capture_raw:
        related_ts = [r["ts"] for r in grouped_logs["capture"] + grouped_logs["ingest"]]
        related_ts.extend(t for t in (_flow_ts(flow) for flow in flows) if isinstance(t, int))
        sections.append(
            {
                "kind": "capture",
                "title": "OpenViking Capture",
                "started_at": min(related_ts, default=None),
                "ended_at": max(related_ts, default=None),
                "stats": capture_stats or [_stat("日志条目", len(grouped_logs["capture"]) + len(grouped_logs["ingest"]))],
                "items": capture_items,
                "raw_refs": capture_raw,
            }
        )

    warning_records = grouped_logs["warning"]
    if warning_records:
        sections.append(
            {
                "kind": "warning",
                "title": "OpenViking Warnings",
                "started_at": warning_records[0]["ts"],
                "ended_at": warning_records[-1]["ts"],
                "stats": [_stat("警告数", len(warning_records))],
                "items": [
                    _item("Warning", record["message"].replace("openviking:", "", 1).strip(), tone="warning")
                    for record in warning_records
                ],
                "raw_refs": [_raw_ref("gateway log", record["raw"]) for record in warning_records[:6]],
            }
        )

    return sections


def build_engine_payload(trace: dict[str, Any], *, context: dict[str, Any]) -> dict[str, Any]:
    lcm_entries = _matching_lcm_entries(trace, lcm_entries=context.get("lcm_entries") or [])
    if lcm_entries:
        sections = _build_lossless_sections(lcm_entries)
        return {
            "id": "lossless-claw",
            "label": "lossless-claw",
            "summary": [
                _stat("诊断条目", len(lcm_entries)),
                _stat("section 数", len(sections)),
            ],
            "sections": sections,
        }

    openviking_logs, openviking_flows = _matching_openviking_records(
        trace,
        gateway_records=context.get("gateway_records") or [],
        http_flows=context.get("http_flows") or [],
    )
    if openviking_logs or openviking_flows:
        sections = _build_openviking_sections(openviking_logs, openviking_flows)
        return {
            "id": "openviking",
            "label": "OpenViking",
            "summary": [
                _stat("gateway 日志", len(openviking_logs)),
                _stat("HTTP 流量", len(openviking_flows)),
                _stat("section 数", len(sections)),
            ],
            "sections": sections,
        }

    return {
        "id": "unknown",
        "label": "unknown",
        "summary": [],
        "sections": [],
    }
