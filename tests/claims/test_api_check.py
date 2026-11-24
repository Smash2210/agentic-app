"""GET /claims/{id}/check (contracts/claims-api.md; spec US1, SC-005)."""

import pytest
from fastapi.testclient import TestClient

from agentic_app.app import create_app
from agentic_app.claims import store
from agentic_app.schemas import ClaimIn

CONTRACT_BODY = {
    "employee_id": "E-001",
    "trip": {"destination_city": "Berlin", "start_date": "2026-03-10", "end_date": "2026-03-12"},
    "lines": [
        {"date": "2026-03-10", "category": "meal", "merchant": "Cafe Roma",
         "amount": "50.00", "currency": "EUR", "receipt_attached": True},
        {"date": "2026-03-10", "category": "meal", "merchant": "Imbiss 24",
         "amount": "30.00", "currency": "USD", "receipt_attached": False},
        {"date": "2026-03-10", "category": "lodging", "merchant": "Hotel Mitte",
         "amount": "400.00", "currency": "EUR", "receipt_attached": True, "nights": 2},
    ],
}

TAXI_CLAIM = {
    "employee_id": "E-001",
    "trip": {"destination_city": "Paris", "start_date": "2026-04-01", "end_date": "2026-04-02"},
    "lines": [
        {"date": "2026-04-01", "category": "transport", "merchant": "Taxi Paris",
         "amount": "20.00", "currency": "EUR", "receipt_attached": False},
    ],
}


@pytest.fixture
def client(db_path, policy_dir):
    return TestClient(create_app(db_path, policy_dir))


def add(db_path, body: dict) -> int:
    conn = store.connect(db_path)
    try:
        return store.add_claim(conn, ClaimIn.model_validate(body)).id
    finally:
        conn.close()


def test_check_returns_contract_shape(client, db_path):
    claim_id = add(db_path, CONTRACT_BODY)

    response = client.get(f"/claims/{claim_id}/check")

    assert response.status_code == 200
    body = response.json()
    assert body["claim_id"] == claim_id
    assert [line["reimbursable_usd"] for line in body["lines"]] == ["54.00", "0.00", "360.00"]
    assert [v["rule_id"] for v in body["violations"]] == [
        "RECEIPT_MISSING", "LODGING_NIGHTLY_CAP", "LODGING_NIGHTLY_CAP",
    ]
    assert body["violations"][1]["excess_usd"] == "36.00"
    assert body["per_diem"]["amount_usd"] == "150.00"
    assert body["lines_reimbursable_usd"] == "414.00"
    assert body["total_reimbursable_usd"] == "564.00"


def test_money_is_serialised_as_strings(client, db_path):
    body = client.get(f"/claims/{add(db_path, CONTRACT_BODY)}/check").json()

    assert isinstance(body["total_reimbursable_usd"], str)
    assert all(isinstance(line["claimed_usd"], str) for line in body["lines"])


def test_unknown_claim_is_404(client):
    response = client.get("/claims/99/check")

    assert response.status_code == 404
    assert response.json() == {"detail": "Claim 99 not found"}


def test_later_claims_do_not_change_an_earlier_result(client, db_path):
    first = add(db_path, TAXI_CLAIM)
    before = client.get(f"/claims/{first}/check").json()

    second = add(db_path, TAXI_CLAIM)  # repeats the taxi line

    assert client.get(f"/claims/{first}/check").json() == before
    later = client.get(f"/claims/{second}/check").json()
    assert [v["rule_id"] for v in later["violations"]] == ["DUPLICATE"]
    assert later["lines"][0]["flagged_for_review"] is True


def test_other_employees_claims_are_not_duplicates(client, db_path):
    add(db_path, TAXI_CLAIM)
    other = add(db_path, {**TAXI_CLAIM, "employee_id": "E-002"})

    assert client.get(f"/claims/{other}/check").json()["violations"] == []
