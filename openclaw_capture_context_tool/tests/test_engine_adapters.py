from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "capture_tool"))

from tools.context_capture.engine_adapters import build_engine_payload, extract_trace_preview, load_diagnostics_context


def _make_trace(start_ts: int, end_ts: int, *, user_text: str = "hello world") -> dict[str, object]:
    return {
        "events": [
            SimpleNamespace(
                ts=start_ts,
                direction="user->gateway",
                channel="ws",
                event_type="user_input",
                payload_full={"text": user_text},
            ),
            SimpleNamespace(
                ts=end_ts,
                direction="gateway->ui",
                channel="ws",
                event_type="ui_final",
                payload_full={"text": "ok"},
            ),
        ]
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


class EngineAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_lcm_path = os.environ.get("LCM_DIAGNOSTICS_PATH")

    def tearDown(self) -> None:
        if self._old_lcm_path is None:
            os.environ.pop("LCM_DIAGNOSTICS_PATH", None)
        else:
            os.environ["LCM_DIAGNOSTICS_PATH"] = self._old_lcm_path

    def test_build_engine_payload_detects_lossless_claw(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lcm_path = root / "lcm-diagnostics.jsonl"
            _write_jsonl(
                lcm_path,
                [
                    {"ts": 1_000, "stage": "bootstrap_entry", "data": {"sessionFile": "demo.md"}},
                    {"ts": 1_500, "stage": "assemble_output", "data": {"outputMessagesCount": 3, "estimatedTokens": 120, "tokensSaved": 40}},
                    {"ts": 2_000, "stage": "ingest", "data": {"role": "assistant", "seq": 9, "tokenCount": 88, "contentPreview": "saved memory"}},
                ],
            )
            os.environ["LCM_DIAGNOSTICS_PATH"] = str(lcm_path)

            data_dir = root / "capture"
            data_dir.mkdir()
            context = load_diagnostics_context(data_dir)
            payload = build_engine_payload(_make_trace(900, 1_900), context=context)

            self.assertEqual(payload["id"], "lossless-claw")
            titles = [section["title"] for section in payload["sections"]]
            self.assertIn("Bootstrap", titles)
            self.assertIn("Context Assemble", titles)
            self.assertIn("Ingest", titles)

    def test_build_engine_payload_detects_openviking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["LCM_DIAGNOSTICS_PATH"] = str(root / "missing-lcm.jsonl")
            data_dir = root / "capture"
            data_dir.mkdir()

            _write_jsonl(
                data_dir / "gateway.log.jsonl",
                [
                    {
                        "time": "2026-03-23T10:00:00.000Z",
                        "1": "openviking: switched to agentId=agent-1 for before_prompt_build",
                    },
                    {
                        "time": "2026-03-23T10:00:00.500Z",
                        "1": 'openviking: capture-check shouldCapture=true reason=semantic newMsgCount=2 text="remember the user likes rust"',
                    },
                    {
                        "time": "2026-03-23T10:00:01.000Z",
                        "1": "openviking: auto-captured 2 new messages, extracted 1 memories",
                    },
                ],
            )
            _write_jsonl(
                data_dir / "raw.jsonl",
                [
                    {
                        "ts": 1_774_627_200_100,
                        "channel": "http",
                        "direction": "request",
                        "method": "POST",
                        "url": "http://127.0.0.1:1933/api/v1/search/find",
                        "flow_id": "flow-1",
                        "body_text": json.dumps({"query": "rust", "target_uri": "viking://user/memories", "limit": 20}),
                    },
                    {
                        "ts": 1_774_627_200_180,
                        "channel": "http",
                        "direction": "response",
                        "method": "POST",
                        "url": "http://127.0.0.1:1933/api/v1/search/find",
                        "flow_id": "flow-1",
                        "status_code": 200,
                        "body_text": json.dumps({"status": "ok", "result": {"memories": [{"uri": "viking://user/default/memories/1"}]}}),
                    },
                    {
                        "ts": 1_774_627_201_100,
                        "channel": "http",
                        "direction": "request",
                        "method": "POST",
                        "url": "http://127.0.0.1:1933/api/v1/sessions/session-1/messages",
                        "flow_id": "flow-2",
                        "body_text": json.dumps({"role": "user", "content": "remember the user likes rust"}),
                    },
                ],
            )

            context = load_diagnostics_context(data_dir)
            payload = build_engine_payload(
                _make_trace(1_774_627_200_000, 1_774_627_201_500, user_text="remember the user likes rust"),
                context=context,
            )

            self.assertEqual(payload["id"], "openviking")
            kinds = [section["kind"] for section in payload["sections"]]
            self.assertIn("recall", kinds)
            self.assertIn("capture", kinds)
            recall_section = next(section for section in payload["sections"] if section["kind"] == "recall")
            self.assertTrue(any("query=rust" in item["value"] for item in recall_section["items"]))

    def test_extract_trace_preview_prefers_user_text(self) -> None:
        preview = extract_trace_preview(_make_trace(100, 200, user_text="please remember my preferred language is rust"))
        self.assertIn("preferred language", preview)


if __name__ == "__main__":
    unittest.main()
