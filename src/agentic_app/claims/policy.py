"""Parse data/policies/*.md into a frozen Policy (research R-02).

Every rate, cap, limit, threshold and percentage comes from the Markdown. If a value cannot be
found exactly once where it is expected, loading fails with a PolicyError naming the file and
section, so a policy edit the parser cannot read is caught at start-up.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType

DOC_FILES = {
    "POL-CURRENCY": "currency.md",
    "POL-LODGING": "lodging.md",
    "POL-MEALS": "meals.md",
    "POL-PERDIEM": "per-diem.md",
    "POL-RECEIPTS": "receipts.md",
}
DEFAULT_CITY_ROW = "any other city"

_NUMBER = r"(\d+(?:\.\d+)?)"
_DOC_ID = re.compile(r"^doc_id:\s*(\S+)\s*$", re.MULTILINE)
_SECTION = re.compile(r"^## (\d+)\. ", re.MULTILINE)


class PolicyError(Exception):
    """A policy document is missing or cannot be parsed."""


@dataclass(frozen=True)
class Policy:
    currency_rates: Mapping[str, Decimal]
    meals_daily_limit_usd: Decimal
    lodging_caps_usd: Mapping[str, Decimal]
    lodging_default_cap_usd: Decimal
    per_diem_rates_usd: Mapping[str, Decimal]
    per_diem_default_rate_usd: Decimal
    travel_day_fraction: Decimal
    same_day_fraction: Decimal
    receipt_threshold_usd: Decimal
    sections: Mapping[str, frozenset[str]]

    def rate_for(self, currency: str) -> Decimal | None:
        """USD per unit of `currency`, or None if the currency is not supported."""
        return self.currency_rates.get(currency)

    def lodging_cap_for(self, city: str) -> Decimal:
        return self.lodging_caps_usd.get(_city_key(city), self.lodging_default_cap_usd)

    def per_diem_rate_for(self, city: str) -> Decimal:
        return self.per_diem_rates_usd.get(_city_key(city), self.per_diem_default_rate_usd)


def _city_key(city: str) -> str:
    return city.strip().casefold()


@dataclass(frozen=True)
class _Doc:
    file_name: str
    sections: dict[str, str]  # section number -> text of that section

    def section(self, number: str) -> str:
        if number not in self.sections:
            raise PolicyError(f"{self.file_name} §{number}: section not found")
        return self.sections[number]

    def table(self, number: str) -> list[tuple[str, Decimal]]:
        """Rows of the Markdown table in a section, as (first cell, number in second cell)."""
        rows = []
        for line in self.section(number).splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not line.lstrip().startswith("|") or len(cells) != 2:
                continue
            if set(cells[1]) <= set("-: "):
                continue  # header separator
            try:
                rows.append((cells[0], Decimal(cells[1])))
            except InvalidOperation:
                continue  # header row
        if not rows:
            raise PolicyError(f"{self.file_name} §{number}: no table rows found")
        return rows

    def bold_number(self, number: str, pattern: str) -> Decimal:
        """The number in a bold phrase, e.g. pattern 'over {n} USD' matches '**over 25 USD**'."""
        regex = re.escape("**" + pattern + "**").replace(re.escape("{n}"), _NUMBER)
        matches = re.findall(regex, self.section(number))
        if len(matches) != 1:
            raise PolicyError(
                f"{self.file_name} §{number}: expected '**{pattern}**' exactly once, "
                f"found {len(matches)}"
            )
        return Decimal(matches[0])


def _read_doc(policy_dir: Path, doc_id: str, file_name: str) -> _Doc:
    path = policy_dir / file_name
    if not path.is_file():
        raise PolicyError(f"{file_name}: file not found in {policy_dir}")
    text = path.read_text(encoding="utf-8")

    found = _DOC_ID.findall(text)
    if found != [doc_id]:
        raise PolicyError(f"{file_name}: expected one 'doc_id: {doc_id}' line, found {found}")

    starts = list(_SECTION.finditer(text))
    sections = {
        match.group(1): text[match.end(): starts[i + 1].start() if i + 1 < len(starts) else None]
        for i, match in enumerate(starts)
    }
    return _Doc(file_name, sections)


def _city_table(doc: _Doc, number: str) -> tuple[Mapping[str, Decimal], Decimal]:
    """A city table split into named cities (case-folded keys) and the 'Any other city' default."""
    cities = {_city_key(city): value for city, value in doc.table(number)}
    if DEFAULT_CITY_ROW not in cities:
        raise PolicyError(f"{doc.file_name} §{number}: no 'Any other city' row")
    default = cities.pop(DEFAULT_CITY_ROW)
    return MappingProxyType(cities), default


def _percent(value: Decimal) -> Decimal:
    return value.scaleb(-2)  # 75 (%) -> 0.75


def load_policy(policy_dir: Path) -> Policy:
    docs = {
        doc_id: _read_doc(Path(policy_dir), doc_id, file_name)
        for doc_id, file_name in DOC_FILES.items()
    }
    currency, lodging, meals = docs["POL-CURRENCY"], docs["POL-LODGING"], docs["POL-MEALS"]
    per_diem, receipts = docs["POL-PERDIEM"], docs["POL-RECEIPTS"]

    lodging_caps, lodging_default = _city_table(lodging, "1")
    per_diem_rates, per_diem_default = _city_table(per_diem, "1")

    return Policy(
        currency_rates=MappingProxyType(dict(currency.table("2"))),
        meals_daily_limit_usd=meals.bold_number("1", "{n} USD per calendar day"),
        lodging_caps_usd=lodging_caps,
        lodging_default_cap_usd=lodging_default,
        per_diem_rates_usd=per_diem_rates,
        per_diem_default_rate_usd=per_diem_default,
        travel_day_fraction=_percent(per_diem.bold_number("2", "{n}%")),
        same_day_fraction=_percent(per_diem.bold_number("3", "one day at {n}%")),
        receipt_threshold_usd=receipts.bold_number("1", "over {n} USD"),
        sections=MappingProxyType(
            {doc_id: frozenset(doc.sections) for doc_id, doc in docs.items()}
        ),
    )
