"""Agent Engine deployment of root_agent (spec 005 FR-510). Deployment is deferred by choice (M10):
this file is the configuration, and --dry-run exercises it locally without any Google Cloud call.

    uv run python deploy/deploy.py --dry-run         # local: the same AdkApp Agent Engine would host
    uv run python deploy/deploy.py --deploy --project P --location us-central1 --staging-bucket gs://B
                                                      # NOT run in M10 (needs a GCP project)

On Agent Engine the app runs in Google's container: the package and policy data ship as extra
packages, the API key comes from Secret Manager, and the claims store would move from the bundled
SQLite file to Cloud SQL before real use (sessions too: VertexAiSessionService instead of memory).
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CONFIG = {
    "display_name": "expense-policy-copilot",
    "description": "Answers travel and expense policy questions and checks stored claims (read-only).",
    # Same pins as pyproject.toml; Agent Engine installs these in its container.
    "requirements": ["google-adk>=2.15.1", "google-genai>=2.34,<3", "google-cloud-aiplatform[agent_engines]>=2.10",
                     "rank-bm25>=0.2.2", "python-dotenv>=1.2.4", "pydantic>=2"],
    # The package plus the policy documents, the passage-embedding cache and a seeded claims DB.
    "extra_packages": ["src/agentic_app", "data/policies", "data/index", "data/claims.db"],
    "env_vars": {
        "GEMINI_MODEL": "gemini-3.5-flash-lite",
        "GEMINI_FALLBACK_MODELS": "gemini-3.5-flash,gemini-3.6-flash",
        "POLICY_DIR": "data/policies",
        "CLAIMS_DB_PATH": "data/claims.db",
        "AGENT_MAX_STEPS": "8",
        # GOOGLE_API_KEY: a Secret Manager SecretRef(secret="gemini-api-key", version="latest")
    },
}


def app():
    from vertexai.agent_engines import AdkApp

    from agentic_app.agents.claims_agent import root_agent

    return AdkApp(agent=root_agent, enable_tracing=False)


def dry_run(message: str) -> int:
    """Everything up to the upload, with no Google Cloud call:
    1. build the AdkApp that Agent Engine would host and serialize it with cloudpickle, as
       agent_engines.create does before uploading;
    2. query the same root_agent through ADK's local runner on the AI Studio key.
    AdkApp.set_up()/stream_query() are NOT used locally: set_up() forces the Vertex AI backend and
    picks up any gcloud default project, which would be a call to Google Cloud."""
    import os

    import cloudpickle

    from agentic_app.agents import claims_agent as ca

    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true"):
        sys.exit("refusing: GOOGLE_GENAI_USE_VERTEXAI is set; the dry run must not reach Google Cloud")
    print("config:", CONFIG)
    blob = cloudpickle.dumps(app())
    print(f"AdkApp built and serialized: {len(blob):,} bytes (what agent_engines.create would upload)")

    def show(event):
        for part in (event.content.parts if event.content and event.content.parts else []):
            if part.function_call:
                print("CALL  ", part.function_call.name, dict(part.function_call.args or {}))
            elif part.function_response:
                print("RESULT", part.function_response.name, (part.function_response.response or {}).get("status"))

    final = ca.run(ca.root_agent, message, show)
    print("FINAL ", final)
    return 0 if final else 1


def deploy(project: str, location: str, staging_bucket: str) -> None:  # pragma: no cover
    import vertexai
    from vertexai import agent_engines

    vertexai.init(project=project, location=location, staging_bucket=staging_bucket)
    remote = agent_engines.create(app(), **CONFIG)
    print("deployed:", remote.resource_name)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--deploy", action="store_true")
    p.add_argument("--project")
    p.add_argument("--location", default="us-central1")
    p.add_argument("--staging-bucket")
    p.add_argument("--message", default="What is the daily limit for meals?")
    a = p.parse_args()
    if a.deploy:
        if not (a.project and a.staging_bucket):
            sys.exit("--deploy needs --project and --staging-bucket (deployment is deferred in M10)")
        deploy(a.project, a.location, a.staging_bucket)
        return 0
    return dry_run(a.message)


if __name__ == "__main__":
    sys.exit(main())
