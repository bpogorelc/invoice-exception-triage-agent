"""Delete the deployed Agent Runtime resource."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from invoice_exception_triage_agent.config import get_settings  # noqa: E402


def main() -> int:
    settings = get_settings()
    resource = settings.agent_engine_resource_name
    saved = ROOT / "evaluation" / "remote_agent.json"
    if not resource and saved.exists():
        resource = json.loads(saved.read_text(encoding="utf-8")).get("resource_name")
    if not resource:
        print("Nothing to clean up: no AGENT_ENGINE_RESOURCE_NAME / remote_agent.json.")
        return 0
    if not settings.google_cloud_project:
        print("GOOGLE_CLOUD_PROJECT is required.")
        return 2

    import vertexai

    client = vertexai.Client(
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
    )
    remote_agent = client.agent_engines.get(name=resource)
    remote_agent.delete(force=True)
    print(f"Deleted {resource}")
    if saved.exists():
        saved.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
