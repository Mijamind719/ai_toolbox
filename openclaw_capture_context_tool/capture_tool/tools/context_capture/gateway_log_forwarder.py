"""Forward gateway stdout lines into structured JSONL records."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_line(raw_line: str) -> str:
    line = raw_line.rstrip("\r\n")
    line = ANSI_ESCAPE_RE.sub("", line)
    return line.strip()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: gateway_log_forwarder.py <output-jsonl>", file=sys.stderr)
        return 2

    output_path = Path(sys.argv[1]).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("a", encoding="utf-8") as output:
        for raw_line in sys.stdin:
            line = _clean_line(raw_line)
            if not line:
                continue
            record = {
                "time": _utc_now_iso(),
                "1": line,
            }
            output.write(json.dumps(record, ensure_ascii=False))
            output.write("\n")
            output.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
