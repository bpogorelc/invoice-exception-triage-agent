"""Deploy via the official ADK CLI to Google Cloud Agent Runtime (Agent Engine).

Docs: https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/quickstart-adk
      https://adk.dev (adk deploy agent_engine)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from invoice_exception_triage_agent.config import get_settings  # noqa: E402


def main() -> int:
    settings = get_settings()
    if not settings.google_cloud_project:
        print("GOOGLE_CLOUD_PROJECT is required for deployment.")
        return 2

    agent_dir = ROOT / "invoice_exception_triage_agent"
    cmd = [
        sys.executable,
        "-m",
        "google.adk.cli",
        "deploy",
        "agent_engine",
        "--project",
        settings.google_cloud_project,
        "--region",
        settings.google_cloud_location,
        "--display_name",
        "Invoice Exception Triage Agent",
        str(agent_dir),
    ]

    env = os.environ.copy()
    env.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
    env.setdefault("GOOGLE_CLOUD_PROJECT", settings.google_cloud_project)
    env.setdefault("GOOGLE_CLOUD_LOCATION", settings.google_cloud_location)
    env.setdefault("GOOGLE_GENAI_MODEL", settings.model_name)

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT), env=env, check=False)
    if result.returncode != 0:
        return result.returncode

    # Best-effort: capture resource name if the CLI printed/saved one.
    out = ROOT / "evaluation" / "remote_agent.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        out.write_text(
            json.dumps(
                {
                    "note": (
                        "Deployment finished. Copy the reasoningEngine resource name "
                        "from the CLI output into AGENT_ENGINE_RESOURCE_NAME."
                    ),
                    "project": settings.google_cloud_project,
                    "location": settings.google_cloud_location,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    print(
        "Set AGENT_ENGINE_RESOURCE_NAME to the deployed reasoningEngine resource, "
        "then run: python scripts/smoke_remote.py"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
