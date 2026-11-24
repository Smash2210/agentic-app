"""Static checks that keep the rules engine pure and money float-free (constitution II–IV).

rules.py must not do I/O, read the clock, use randomness or call a model, and must not contain any
policy number: every limit comes from the Policy object (spec FR-011).
"""

import ast
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "agentic_app"
RULES = SRC / "claims" / "rules.py"
FLOAT_FREE = [*sorted((SRC / "claims").glob("*.py")), SRC / "schemas.py"]

BANNED_MODULES = {"sqlite3", "os", "pathlib", "random", "time", "agentic_app.llm", "google"}
ALLOWED_NUMBERS = {Decimal(0), Decimal(1)}


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def imported_modules(tree: ast.Module) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def is_banned(module: str) -> bool:
    return any(module == banned or module.startswith(banned + ".") for banned in BANNED_MODULES)


def test_rules_imports_no_io_clock_randomness_or_llm():
    banned = sorted(m for m in imported_modules(parse(RULES)) if is_banned(m))
    assert banned == []


def test_rules_never_reads_the_clock():
    calls = [
        node.func.attr
        for node in ast.walk(parse(RULES))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"now", "today", "utcnow"}
    ]
    assert calls == []


@pytest.mark.parametrize("path", FLOAT_FREE, ids=lambda p: p.name)
def test_no_float_calls(path):
    lines = [
        node.lineno
        for node in ast.walk(parse(path))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float"
    ]
    assert lines == [], f"float() used in {path.name} at lines {lines}"


def numeric_literals(tree: ast.Module) -> list[tuple[int, str]]:
    """Every number written in the source: int/float constants, and numeric strings in Decimal()."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            found.append((node.lineno, repr(node.value), Decimal(str(node.value))))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == "Decimal"
            and node.args and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            try:
                value = Decimal(node.args[0].value)
            except InvalidOperation:
                continue
            found.append((node.lineno, f'Decimal("{node.args[0].value}")', value))
    return [(line, text) for line, text, value in found if value not in ALLOWED_NUMBERS]


def per_diem_day_count_lines(tree: ast.Module) -> set[int]:
    """Lines of the `full_days = ...` assignment inside `_per_diem`.

    The integer 2 there is structural, not a policy number: a multi-day trip has exactly two
    travel days (the first and the last), and POL-PERDIEM §2 sets their rate, which comes from
    Policy. That assignment is the only place the literal 2 is allowed.
    """
    for func in ast.walk(tree):
        if isinstance(func, ast.FunctionDef) and func.name == "_per_diem":
            return {
                node.lineno
                for node in ast.walk(func)
                if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "full_days" for t in node.targets)
            }
    return set()


def test_rules_contains_no_policy_numbers():
    # 0 and 1 are allowed in any form, e.g. Decimal("0.00"); everything else comes from Policy,
    # except the structural 2 in the per-diem day count (see per_diem_day_count_lines).
    tree = parse(RULES)
    allowed_lines = per_diem_day_count_lines(tree)
    found = [
        (line, text) for line, text in numeric_literals(tree)
        if not (text == "2" and line in allowed_lines)
    ]
    assert found == []


def test_numeric_literal_scan_catches_hidden_numbers():
    # Guard for the scan itself, so a broken scanner cannot pass silently.
    tree = ast.parse('x = 75\ny = Decimal("25.00")\nz = Decimal("0.00") + 1')
    assert numeric_literals(tree) == [(1, "75"), (2, 'Decimal("25.00")')]


def test_shared_rule_state_cannot_be_changed():
    # Constitution III / contracts/claims-api.md: no module-level mutable state in the engine.
    import dataclasses

    from agentic_app.claims import rules

    assert isinstance(rules._RULE_ORDER, tuple)
    for citation in [*rules.RULE_CITATIONS.values(), *rules.PER_DIEM_CITATIONS.values()]:
        assert isinstance(citation.sections, tuple)
        with pytest.raises(dataclasses.FrozenInstanceError):
            citation.doc_id = "POL-CHANGED"  # type: ignore[misc]
