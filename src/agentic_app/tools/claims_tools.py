"""The claims agent's tools (spec 004 FR-401, FR-402). They reuse the spec 001 store and rules
engine and the spec 003 policy index; each is wrapped by resilience.resilient, so it returns
{"status": "ok", ...} or a typed error result, never an exception.

Amounts are returned exactly as the rules engine computed them (strings); the model only repeats them.
"""

import os
from functools import lru_cache
from pathlib import Path

from agentic_app.claims import store
from agentic_app.claims.policy import Policy, load_policy
from agentic_app.claims.rules import check_claim as run_rules
from agentic_app.rag import embeddings
from agentic_app.rag.index import PolicyIndex
from agentic_app.tools.errors import ToolBadInput
from agentic_app.tools.resilience import resilient

SEARCH_TIMEOUT_S = 10.0  # one embedding call over the network
DB_TIMEOUT_S = 5.0

SEARCH_FALLBACK = ("Policy search is unavailable. Use the policy references (doc_id and section) in "
                   "check_claim results if you have them, and tell the user that policy search was "
                   "unavailable. Never cite policy from memory.")
CLAIM_FALLBACK = ("Tell the user which claim could not be {verb} and why. Give no amounts for it "
                  "and never compute amounts yourself.")

# Replaced in tests: the question embedder (spec 003 embeddings.gemini_embed).
embed = embeddings.gemini_embed


def _db_path() -> Path:
    return Path(os.getenv("CLAIMS_DB_PATH", "data/claims.db"))


def _policy_dir() -> Path:
    return Path(os.getenv("POLICY_DIR", "data/policies"))


@lru_cache(maxsize=2)
def _policy(policy_dir: Path) -> Policy:
    return load_policy(policy_dir)


@lru_cache(maxsize=2)
def _index(policy_dir: Path) -> PolicyIndex:
    from agentic_app.rag.chunks import load_chunks

    chunks = load_chunks(policy_dir)
    cache = policy_dir.parent / "index" / "embeddings.json"
    return PolicyIndex(chunks, embeddings.passage_vectors(chunks, cache))


def _load(tool: str, claim_id: int):
    if not isinstance(claim_id, int) or claim_id < 1:
        raise ToolBadInput(tool, f"claim_id must be a positive integer, got {claim_id!r}")
    conn = store.connect(_db_path())
    try:
        claim = store.get_claim(conn, claim_id)
        if claim is None:
            raise ToolBadInput(tool, f"claim {claim_id} not found")
        return claim, store.prior_lines(conn, claim.employee_id, claim.id)
    finally:
        conn.close()


@resilient("search_policy", timeout_s=SEARCH_TIMEOUT_S, fallback=SEARCH_FALLBACK)
def search_policy(query: str) -> dict:
    """Search the travel and expense policy. Returns the most relevant passages, each with an ID
    like POL-MEALS#1 (document and section) to cite.

    Args:
        query: A short search query, e.g. "daily meal limit".
    """
    query = (query or "").strip()
    if not 1 <= len(query) <= 500:
        raise ToolBadInput("search_policy", "query must be 1-500 characters")
    index = _index(_policy_dir())
    hits = index.search(query, embed([query], "RETRIEVAL_QUERY")[0])
    return {"status": "ok", "passages": [
        {"id": h.chunk.id, "title": f"{h.chunk.doc_title} — {h.chunk.title}", "text": h.chunk.body}
        for h in hits]}


@resilient("get_claim", timeout_s=DB_TIMEOUT_S, fallback=CLAIM_FALLBACK.format(verb="loaded"))
def get_claim(claim_id: int) -> dict:
    """Load a stored expense claim: employee, trip and expense lines as submitted.

    Args:
        claim_id: The claim number, e.g. 3.
    """
    claim, _ = _load("get_claim", claim_id)
    return {"status": "ok", "claim": claim.model_dump(mode="json")}


@resilient("check_claim", timeout_s=DB_TIMEOUT_S, fallback=CLAIM_FALLBACK.format(verb="checked"))
def check_claim(claim_id: int) -> dict:
    """Check a stored claim against the expense policy with the deterministic rules engine.
    Returns every violation with its policy citation, the per diem and the reimbursable totals in
    USD. These are the only amounts you may report.

    Args:
        claim_id: The claim number, e.g. 3.
    """
    claim, prior = _load("check_claim", claim_id)
    result = run_rules(claim, prior, _policy(_policy_dir()))
    return {"status": "ok", "check": result.model_dump(mode="json")}
