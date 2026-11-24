import dataclasses
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from agentic_app.claims.policy import Policy, PolicyError, load_policy


@pytest.fixture(scope="module")
def loaded(policy_dir) -> Policy:
    return load_policy(policy_dir)


@pytest.fixture
def policy_copy(tmp_path, policy_dir) -> Path:
    """A writable copy of data/policies for failure cases."""
    target = tmp_path / "policies"
    shutil.copytree(policy_dir, target)
    return target


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text, f"fixture text not found in {path.name}: {old!r}"
    path.write_text(text.replace(old, new, 1))


# --- values match data/policies/*.md -----------------------------------------------------------


def test_currency_rates(loaded):  # POL-CURRENCY §2
    assert dict(loaded.currency_rates) == {
        "USD": Decimal("1.00"),
        "EUR": Decimal("1.08"),
        "GBP": Decimal("1.27"),
        "INR": Decimal("0.012"),
    }


def test_meals_daily_limit(loaded):  # POL-MEALS §1
    assert loaded.meals_daily_limit_usd == Decimal("100")


def test_lodging_caps(loaded):  # POL-LODGING §1
    assert dict(loaded.lodging_caps_usd) == {"berlin": Decimal("180"), "london": Decimal("220")}
    assert loaded.lodging_default_cap_usd == Decimal("140")


def test_per_diem_rates(loaded):  # POL-PERDIEM §1
    assert dict(loaded.per_diem_rates_usd) == {"berlin": Decimal("60"), "london": Decimal("70")}
    assert loaded.per_diem_default_rate_usd == Decimal("45")


def test_per_diem_fractions(loaded):  # POL-PERDIEM §2, §3
    assert loaded.travel_day_fraction == Decimal("0.75")
    assert loaded.same_day_fraction == Decimal("0.75")


def test_receipt_threshold(loaded):  # POL-RECEIPTS §1
    assert loaded.receipt_threshold_usd == Decimal("25")


def test_sections(loaded):
    assert dict(loaded.sections) == {
        "POL-CURRENCY": frozenset({"1", "2", "3", "4"}),
        "POL-LODGING": frozenset({"1", "2", "3", "4"}),
        "POL-MEALS": frozenset({"1", "2", "3"}),
        "POL-PERDIEM": frozenset({"1", "2", "3", "4"}),
        "POL-RECEIPTS": frozenset({"1", "2", "3", "4"}),
    }


def test_all_numbers_are_decimal(loaded):
    values = [
        loaded.meals_daily_limit_usd,
        loaded.lodging_default_cap_usd,
        loaded.per_diem_default_rate_usd,
        loaded.travel_day_fraction,
        loaded.same_day_fraction,
        loaded.receipt_threshold_usd,
        *loaded.currency_rates.values(),
        *loaded.lodging_caps_usd.values(),
        *loaded.per_diem_rates_usd.values(),
    ]
    assert all(type(v) is Decimal for v in values)


# --- lookups ------------------------------------------------------------------------------------


@pytest.mark.parametrize("city", ["Berlin", "berlin", "  BERLIN "])
def test_city_lookup_ignores_case_and_spaces(loaded, city):
    assert loaded.lodging_cap_for(city) == Decimal("180")
    assert loaded.per_diem_rate_for(city) == Decimal("60")


def test_unknown_city_gets_default(loaded):
    assert loaded.lodging_cap_for("Paris") == Decimal("140")
    assert loaded.per_diem_rate_for("Paris") == Decimal("45")


def test_currency_lookup(loaded):
    assert loaded.rate_for("EUR") == Decimal("1.08")
    assert loaded.rate_for("JPY") is None


# --- immutability -------------------------------------------------------------------------------


def test_policy_is_frozen(loaded):
    with pytest.raises(dataclasses.FrozenInstanceError):
        loaded.meals_daily_limit_usd = Decimal("1000")  # type: ignore[misc]


def test_policy_mappings_are_read_only(loaded):
    with pytest.raises(TypeError):
        loaded.currency_rates["JPY"] = Decimal("0.0067")  # type: ignore[index]
    with pytest.raises(TypeError):
        loaded.lodging_caps_usd["paris"] = Decimal("999")  # type: ignore[index]


# --- parse failures -----------------------------------------------------------------------------


def test_missing_file(policy_copy):
    (policy_copy / "meals.md").unlink()
    with pytest.raises(PolicyError, match="meals.md"):
        load_policy(policy_copy)


def test_missing_doc_id(policy_copy):
    _edit(policy_copy / "receipts.md", "doc_id: POL-RECEIPTS\n", "")
    with pytest.raises(PolicyError, match="receipts.md.*doc_id"):
        load_policy(policy_copy)


def test_missing_default_city_row(policy_copy):
    _edit(policy_copy / "lodging.md", "| Any other city | 140 |\n", "")
    with pytest.raises(PolicyError, match=r"lodging.md §1.*Any other city"):
        load_policy(policy_copy)


def test_bold_value_missing(policy_copy):
    _edit(policy_copy / "meals.md", "**100 USD per calendar day**", "100 USD per calendar day")
    with pytest.raises(PolicyError, match=r"meals.md §1"):
        load_policy(policy_copy)


def test_bold_value_present_twice(policy_copy):
    _edit(
        policy_copy / "receipts.md",
        "measured after conversion",
        "(**over 30 USD** for some) measured after conversion",
    )
    with pytest.raises(PolicyError, match=r"receipts.md §1"):
        load_policy(policy_copy)


def test_per_diem_percentage_missing(policy_copy):
    _edit(policy_copy / "per-diem.md", "**one day at 75%**", "one day at 75%")
    with pytest.raises(PolicyError, match=r"per-diem.md §3"):
        load_policy(policy_copy)
