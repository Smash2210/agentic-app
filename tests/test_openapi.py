import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_committed_openapi_matches_the_code():
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "exports_openapi.py"), "--check"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr