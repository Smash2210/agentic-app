"""Load the synthetic seed claims into an empty database (research R-13).

    uv run python -m agentic_app.claims.seed --db data/claims.db
"""

import argparse
import json
import sys
from pathlib import Path

from agentic_app.claims import store
from agentic_app.schemas import ClaimIn

DEFAULT_SEED_FILE = Path("data/seed/claims.json")


def load_seed_claims(seed_file: Path) -> list[ClaimIn]:
    """Validate every seed claim with the API's input model; `expected_*` keys are dropped."""
    raw = json.loads(seed_file.read_text(encoding="utf-8"))
    return [
        ClaimIn.model_validate({k: v for k, v in entry.items() if not k.startswith("expected_")})
        for entry in raw
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load seed claims into an empty database.")
    parser.add_argument("--db", required=True, type=Path, help="SQLite database file")
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED_FILE, help="seed JSON file")
    args = parser.parse_args(argv)

    claims = load_seed_claims(args.seed)
    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = store.connect(args.db)
    try:
        store.init_db(conn)
        if conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]:
            print(f"Database {args.db} is not empty; refusing to load seed data.", file=sys.stderr)
            return 1
        for claim in claims:  # in file order, so claim IDs follow the seed's submission order
            store.add_claim(conn, claim)
    finally:
        conn.close()
    print(f"Loaded {len(claims)} claims")
    return 0


if __name__ == "__main__":
    sys.exit(main())
