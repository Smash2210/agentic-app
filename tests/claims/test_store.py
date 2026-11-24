from datetime import date
from decimal import Decimal

import pytest

from agentic_app.claims import store
from agentic_app.schemas import ClaimIn, PriorLine


def claim_in(employee_id: str = "E-001", merchant: str = "Cafe Roma") -> ClaimIn:
    return ClaimIn.model_validate(
        {
            "employee_id": employee_id,
            "trip": {"destination_city": "Berlin", "start_date": "2026-03-10",
                     "end_date": "2026-03-12"},
            "lines": [
                {"date": "2026-03-10", "category": "meal", "merchant": merchant,
                 "amount": "50.00", "currency": "EUR", "receipt_attached": True},
                {"date": "2026-03-11", "category": "lodging", "merchant": "Hotel Mitte",
                 "amount": "400.00", "currency": "EUR", "receipt_attached": True, "nights": 2},
            ],
        }
    )


@pytest.fixture
def conn(db_path):
    connection = store.connect(db_path)
    store.init_db(connection)
    yield connection
    connection.close()


def claim_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]


def test_init_db_is_idempotent(conn):
    store.init_db(conn)
    store.add_claim(conn, claim_in())
    store.init_db(conn)
    assert claim_count(conn) == 1


def test_add_claim_assigns_increasing_ids_and_line_numbers(conn):
    first = store.add_claim(conn, claim_in())
    second = store.add_claim(conn, claim_in())
    assert isinstance(first.id, int)
    assert second.id > first.id
    assert [line.line_no for line in first.lines] == [1, 2]


def test_get_claim_round_trips_every_field(conn):
    submitted = claim_in()
    stored = store.add_claim(conn, submitted)
    loaded = store.get_claim(conn, stored.id)

    assert loaded == stored
    assert loaded.employee_id == "E-001"
    assert loaded.trip == submitted.trip
    meal, lodging = loaded.lines
    assert str(meal.amount) == "50.00"  # exact text, not 50 or 50.0
    assert type(meal.amount) is Decimal
    assert meal.nights is None
    assert lodging.nights == 2
    assert meal.date == date(2026, 3, 10)
    assert meal.receipt_attached is True
    assert (meal.category, meal.merchant, meal.currency) == ("meal", "Cafe Roma", "EUR")


def test_get_unknown_claim_returns_none(conn):
    assert store.get_claim(conn, 999) is None


def test_money_columns_are_text(conn):
    columns = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(expense_lines)")}
    assert columns["amount"] == "TEXT"


def test_prior_lines_only_returns_earlier_claims_of_the_same_employee(conn):
    first = store.add_claim(conn, claim_in("E-001", merchant="First"))
    store.add_claim(conn, claim_in("E-002", merchant="Other employee"))
    current = store.add_claim(conn, claim_in("E-001", merchant="Current"))
    store.add_claim(conn, claim_in("E-001", merchant="Later"))

    prior = store.prior_lines(conn, "E-001", current.id)

    assert prior == [
        PriorLine(claim_id=first.id, line_no=1, date=date(2026, 3, 10),
                  amount=Decimal("50.00"), currency="EUR", merchant="First"),
        PriorLine(claim_id=first.id, line_no=2, date=date(2026, 3, 11),
                  amount=Decimal("400.00"), currency="EUR", merchant="Hotel Mitte"),
    ]


def test_prior_lines_empty_for_first_claim(conn):
    first = store.add_claim(conn, claim_in())
    assert store.prior_lines(conn, "E-001", first.id) == []


def test_failed_insert_stores_nothing(conn, monkeypatch):
    real_insert_line = store._insert_line
    calls = []

    def fail_on_second_line(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("disk full")
        return real_insert_line(*args, **kwargs)

    monkeypatch.setattr(store, "_insert_line", fail_on_second_line)
    with pytest.raises(RuntimeError):
        store.add_claim(conn, claim_in())

    assert claim_count(conn) == 0
    assert conn.execute("SELECT COUNT(*) FROM expense_lines").fetchone()[0] == 0
