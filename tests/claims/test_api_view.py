"""GET /claims/{id} and GET /claims?employee_id= (contracts/claims-api.md; spec US3, FR-004, FR-005)."""

import pytest
from fastapi.testclient import TestClient

from agentic_app.app import create_app
from agentic_app.claims import store
from agentic_app.schemas import ClaimIn


def body(employee_id: str, merchant: str) -> dict:
    return {
        "employee_id": employee_id,
        "trip": {"destination_city": "Paris", "start_date": "2026-04-01", "end_date": "2026-04-02"},
        "lines": [
            {"date": "2026-04-01", "category": "transport", "merchant": merchant,
             "amount": "20.00", "currency": "EUR", "receipt_attached": False},
            {"date": "2026-04-01", "category": "lodging", "merchant": "Hotel Lumiere",
             "amount": "120.00", "currency": "EUR", "receipt_attached": True},
        ],
    }


@pytest.fixture
def client(db_path, policy_dir):
    return TestClient(create_app(db_path, policy_dir))


@pytest.fixture
def stored(db_path, client):
    """Three claims for E-001 and one for E-002, stored directly (not through POST)."""
    conn = store.connect(db_path)
    try:
        return [
            store.add_claim(conn, ClaimIn.model_validate(body(employee_id, merchant)))
            for employee_id, merchant in [
                ("E-001", "Taxi A"), ("E-002", "Taxi B"), ("E-001", "Taxi C"), ("E-001", "Taxi D"),
            ]
        ]
    finally:
        conn.close()


def test_get_claim_returns_the_stored_claim(client, stored):
    claim = stored[2]

    response = client.get(f"/claims/{claim.id}")

    assert response.status_code == 200
    assert response.json() == claim.model_dump(mode="json")
    assert response.json()["lines"][0]["amount"] == "20.00"
    assert response.json()["lines"][1]["nights"] == 1


def test_get_unknown_claim_is_404(client, stored):
    response = client.get("/claims/99")

    assert response.status_code == 404
    assert response.json() == {"detail": "Claim 99 not found"}


def test_list_claims_for_employee_in_submission_order(client, stored):
    response = client.get("/claims", params={"employee_id": "E-001"})

    assert response.status_code == 200
    claims = response.json()
    assert [c["id"] for c in claims] == [stored[0].id, stored[2].id, stored[3].id]
    assert [c["lines"][0]["merchant"] for c in claims] == ["Taxi A", "Taxi C", "Taxi D"]


def test_list_claims_for_unknown_employee_is_empty(client, stored):
    response = client.get("/claims", params={"employee_id": "E-999"})

    assert response.status_code == 200
    assert response.json() == []


def test_list_claims_requires_employee_id(client):
    response = client.get("/claims")

    assert response.status_code == 422
    assert ["query", "employee_id"] in [error["loc"] for error in response.json()["detail"]]
