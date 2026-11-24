import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "run_review", Path(__file__).resolve().parents[1] / "review" / "run_review.py"
)
run_review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_review)
Verdict, Finding = run_review.Verdict, run_review.Finding


def verdict(spec_violation=False, *risks):
    findings = [Finding(id=f"F{i}", finding="x", file="f.py", risk=r, evidence="e")
                for i, r in enumerate(risks)]
    return Verdict(spec_violation=spec_violation, spec_violation_reason="r" if spec_violation else "",
                   findings=findings)


def test_clean_review_passes():
    assert run_review.blocking_reasons({"security": verdict(), "patterns": verdict(False, "low", "med")}) == []


def test_spec_violation_blocks():
    assert len(run_review.blocking_reasons({"security": verdict(), "patterns": verdict(True)})) == 1


def test_high_risk_finding_blocks():
    assert len(run_review.blocking_reasons({"security": verdict(False, "high", "low")})) == 1