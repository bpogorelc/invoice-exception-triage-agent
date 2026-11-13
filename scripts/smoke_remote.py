"""Remote smoke test against a deployed Agent Runtime resource using INV-1002."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from invoice_exception_triage_agent.config import get_settings  # noqa: E402


async def _async_query(remote_agent, message: str) -> list:
    events = []
    if hasattr(remote_agent, "async_stream_query"):
        async for event in remote_agent.async_stream_query(
            user_id="ap-analyst-demo", message=message
        ):
            events.append(event)
            print(event)
        return events
    for event in remote_agent.stream_query(user_id="ap-analyst-demo", message=message):
        events.append(event)
        print(event)
    return events


def main() -> int:
    settings = get_settings()
    resource = settings.agent_engine_resource_name
    if not resource:
        saved = ROOT / "evaluation" / "remote_agent.json"
        if saved.exists():
            resource = json.loads(saved.read_text(encoding="utf-8")).get("resource_name")
    if not resource:
        print(
            "Cloud verification skipped: set AGENT_ENGINE_RESOURCE_NAME "
            "or deploy first (scripts/deploy_agent_runtime.py)."
        )
        return 2
    if not settings.google_cloud_project:
        print("GOOGLE_CLOUD_PROJECT is required.")
        return 2

    import vertexai

    client = vertexai.Client(
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
    )
    remote_agent = client.agent_engines.get(name=resource)

    message = "Review invoice INV-1002."
    print(f"Querying {resource} with: {message}")
    events = asyncio.run(_async_query(remote_agent, message))

    out = ROOT / "evaluation" / "remote_smoke_inv1002.json"
    out.write_text(json.dumps(events, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out}")

    blob = json.dumps(events, default=str)
    ok = "RECEIPT_DISCREPANCY" in blob or "400" in blob
    eval_path = ROOT / "evaluation" / "results.md"
    if eval_path.exists():
        with eval_path.open("a", encoding="utf-8") as handle:
            handle.write(
                "\n| deployed cloud agent | INV-1002 | RECEIPT_DISCREPANCY | "
                f"{'observed in stream' if ok else 'not observed'} | 400.00 | "
                f"{'see smoke json' if ok else '—'} | Receiving | see smoke json | "
                f"{'yes' if ok else 'NO'} |\n"
            )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
