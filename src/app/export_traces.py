"""Export recent LangSmith traces to local JSONL before retention expires.

LangSmith's free plan keeps traces for 14 days (rolling). This script pulls
the root runs of the project into data/traces_backup/ so the interaction
history survives — runnable manually or on a weekly schedule (GitHub Actions,
n8n, cron). Note: data/logs/questions.jsonl is the app's own primary log;
this export adds the LangSmith-side detail (latency, tokens, errors).

Usage:
    python -m src.app.export_traces [--days 14]
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

from .config import BASE_DIR

BACKUP_DIR = BASE_DIR / "data" / "traces_backup"


def main() -> None:
    days = 14
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])

    try:
        from langsmith import Client
    except ImportError:
        raise SystemExit("langsmith package not installed (it ships with langchain).")

    project = os.getenv("LANGSMITH_PROJECT", "latram-support-agent")
    client = Client()
    since = datetime.now(timezone.utc) - timedelta(days=days)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    out = BACKUP_DIR / f"traces_{datetime.now():%Y%m%d}.jsonl"
    n = 0
    with open(out, "w", encoding="utf-8") as fh:
        for run in client.list_runs(project_name=project, start_time=since,
                                    is_root=True):
            fh.write(json.dumps({
                "id": str(run.id),
                "name": run.name,
                "start_time": run.start_time.isoformat() if run.start_time else None,
                "latency_s": ((run.end_time - run.start_time).total_seconds()
                              if run.end_time and run.start_time else None),
                "total_tokens": getattr(run, "total_tokens", None),
                "error": run.error,
                "input": str(run.inputs)[:500] if run.inputs else None,
                "output": str(run.outputs)[:500] if run.outputs else None,
            }, ensure_ascii=False) + "\n")
            n += 1
    print(f"{n} traces exported -> {out}")


if __name__ == "__main__":
    main()
