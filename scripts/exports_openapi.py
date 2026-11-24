"""Write the Claims API OpenAPI spec to docs/api/openapi.json, or check that it is up to date.

    uv run python scripts/exports_openapi.py          # write
    uv run python scripts/exports_openapi.py --check  # exit 1 if the file is stale (used by CI)
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from agentic_app.app import create_app

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "api" / "openapi.json"


def render() -> str:
    with tempfile.TemporaryDirectory() as tmp:  # a throwaway DB: the spec doesn't depend on data
        app = create_app(Path(tmp) / "claims.db", REPO / "data" / "policies")
        return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the file is stale")
    args = parser.parse_args()

    spec = render()
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != spec:
            print(f"{OUT.relative_to(REPO)} is stale: run scripts/exports_openapi.py", file=sys.stderr)
            return 1
        print(f"{OUT.relative_to(REPO)} is up to date")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(spec, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())