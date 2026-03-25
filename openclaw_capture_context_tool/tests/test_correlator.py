from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "capture_tool"))

from tools.context_capture.correlator import correlate_events
from tools.context_capture.models import EventRecord


class CorrelatorTests(unittest.TestCase):
    def test_internal_or_json_model_response_counts_as_complete(self) -> None:
        traces = correlate_events(
            [
                EventRecord(
                    ts=1_000,
                    direction="user->gateway",
                    channel="http",
                    event_type="user_input",
                    payload_full={"request_flow_id": "flow-1"},
                ),
                EventRecord(
                    ts=1_100,
                    direction="gateway->model",
                    channel="cache_trace",
                    event_type="model_request_internal",
                    payload_full={"request_flow_id": "flow-1"},
                ),
                EventRecord(
                    ts=1_200,
                    direction="model->gateway",
                    channel="cache_trace",
                    event_type="model_response_internal",
                    payload_full={"request_flow_id": "flow-1"},
                ),
                EventRecord(
                    ts=1_250,
                    direction="model->gateway",
                    channel="http",
                    event_type="model_response_json",
                    payload_full={"request_flow_id": "flow-1"},
                ),
            ]
        )

        self.assertEqual(len(traces), 1)
        self.assertNotIn("missing_model_response", traces[0]["missing_reasons"])


if __name__ == "__main__":
    unittest.main()
