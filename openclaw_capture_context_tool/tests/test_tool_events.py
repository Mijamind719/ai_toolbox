from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "capture_tool"))

from tools.context_capture import api
from tools.context_capture.parser import parse_raw_record


class ToolEventParsingTests(unittest.TestCase):
    def test_session_after_emits_current_turn_tool_events_from_cache_trace(self) -> None:
        raw = {
            "stage": "session:after",
            "ts": "2026-03-24T07:38:52.170Z",
            "runId": "resp_demo",
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "old question"}],
                    "timestamp": 1_774_337_800_000,
                },
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "toolCall",
                            "id": "call_old111",
                            "name": "read",
                            "arguments": {"path": "HEARTBEAT.md"},
                        }
                    ],
                    "stopReason": "toolUse",
                    "timestamp": 1_774_337_801_000,
                },
                {
                    "role": "toolResult",
                    "toolCallId": "call_old111",
                    "toolName": "read",
                    "content": [{"type": "text", "text": "ignored old result"}],
                    "timestamp": 1_774_337_802_000,
                },
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "new question"}],
                    "timestamp": 1_774_337_903_000,
                },
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "toolCall",
                            "id": "call_abc123",
                            "name": "web_search",
                            "arguments": {"query": "Beijing weather today", "count": 3},
                        }
                    ],
                    "stopReason": "toolUse",
                    "timestamp": 1_774_337_903_282,
                },
                {
                    "role": "toolResult",
                    "toolCallId": "callabc123",
                    "toolName": "web_search",
                    "content": [{"type": "text", "text": '{"status":"ok"}'}],
                    "details": {"durationMs": 321, "status": "completed"},
                    "timestamp": 1_774_337_910_718,
                },
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "done"}],
                    "timestamp": 1_774_337_912_000,
                },
            ],
        }

        events = parse_raw_record(raw)

        self.assertEqual(
            [event.event_type for event in events],
            ["model_tool_call", "tool_start", "tool_end", "model_response_internal"],
        )

        model_tool_call = events[0]
        self.assertEqual(model_tool_call.direction, "model->gateway")
        self.assertEqual(model_tool_call.payload_full["tool"], "web_search")
        self.assertEqual(model_tool_call.payload_full["tool_call_id"], "call:abc123")
        self.assertEqual(model_tool_call.payload_full["tool_arguments"]["query"], "Beijing weather today")

        tool_start = events[1]
        self.assertEqual(tool_start.direction, "gateway->tool")
        self.assertEqual(tool_start.payload_full["tool"], "web_search")
        self.assertEqual(tool_start.payload_full["tool_call_id"], "call:abc123")
        self.assertEqual(tool_start.payload_full["tool_arguments"]["query"], "Beijing weather today")
        self.assertEqual(tool_start.payload_full["stop_reason"], "toolUse")

        tool_end = events[2]
        self.assertEqual(tool_end.direction, "tool->gateway")
        self.assertEqual(tool_end.payload_full["tool"], "web_search")
        self.assertEqual(tool_end.payload_full["tool_call_id"], "call:abc123")
        self.assertEqual(tool_end.payload_full["duration_ms"], 321)
        self.assertIn('"status":"ok"', tool_end.payload_full["result_text"])
        self.assertNotIn("ignored old result", tool_end.payload_full["result_text"])

    def test_dedupe_tool_events_merges_gateway_log_and_cache_trace(self) -> None:
        gateway_event = SimpleNamespace(
            ts=1_000,
            direction="gateway->tool",
            channel="gateway_log",
            event_type="tool_start",
            payload_full={
                "source": "gateway_log",
                "run_id": "resp_demo",
                "tool": "web_search",
                "tool_call_id": "call_abc123",
                "request_flow_id": "flow-1",
            },
        )
        cache_event = SimpleNamespace(
            ts=1_001,
            direction="gateway->tool",
            channel="cache_trace",
            event_type="tool_start",
            payload_full={
                "source": "cache_trace",
                "run_id": "resp_demo",
                "tool": "web_search",
                "tool_call_id": "callabc123",
                "request_flow_id": "flow-1",
                "tool_arguments": {"query": "Beijing weather today"},
                "message_ts": 1_001,
            },
        )

        deduped = api._dedupe_tool_events([gateway_event, cache_event])

        self.assertEqual(len(deduped), 1)
        merged = deduped[0]
        self.assertEqual(merged.channel, "cache_trace")
        self.assertEqual(merged.payload_full["source"], "merged")
        self.assertEqual(merged.payload_full["tool_call_id"], "call_abc123")
        self.assertEqual(merged.payload_full["tool_arguments"]["query"], "Beijing weather today")

    def test_dedupe_tool_events_merges_model_tool_call_snapshots(self) -> None:
        first = SimpleNamespace(
            ts=1_000,
            direction="model->gateway",
            channel="cache_trace",
            event_type="model_tool_call",
            payload_full={
                "source": "cache_trace",
                "run_id": "resp_demo",
                "tool": "web_search",
                "tool_call_id": "callabc123",
                "tool_arguments": {"query": "Beijing weather today"},
                "message_ts": 1_000,
            },
        )
        second = SimpleNamespace(
            ts=1_001,
            direction="model->gateway",
            channel="cache_trace",
            event_type="model_tool_call",
            payload_full={
                "source": "cache_trace",
                "run_id": "resp_demo",
                "tool": "web_search",
                "tool_call_id": "call_abc123",
                "message_ts": 1_001,
                "stop_reason": "toolUse",
            },
        )

        deduped = api._dedupe_tool_events([first, second])

        self.assertEqual(len(deduped), 1)
        merged = deduped[0]
        self.assertEqual(merged.payload_full["tool_arguments"]["query"], "Beijing weather today")
        self.assertEqual(merged.payload_full["stop_reason"], "toolUse")


if __name__ == "__main__":
    unittest.main()
