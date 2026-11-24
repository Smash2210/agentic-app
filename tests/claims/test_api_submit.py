"""POST /claims (contracts/claims-api.md; spec US2, FR-001–FR-003, SC-006)."""

import copy

import pytest
from fastapi.testclient import TestClient

from agentic_app.app import create_app
from agentic_app.claims import store

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


@pytest.fixture
def client(db_path, policy_dir):
    return TestClient(create_app(db_path, policy_dir))


def body_with(change) -> dict:
    body = copy.deepcopy(CONTRACT_BODY)
    change(body)
    return body


def claim_count(db_path) -> int:
    conn = store.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    finally:
        conn.close()


def test_valid_claim_is_stored_and_returned(client):
    response = client.post("/claims", json=CONTRACT_BODY)

    assert response.status_code == 201
    claim = response.json()
    assert isinstance(claim["id"], int)
    assert claim["employee_id"] == "E-001"
    assert claim["trip"] == CONTRACT_BODY["trip"]
    assert [line["line_no"] for line in claim["lines"]] == [1, 2, 3]
    assert [line["nights"] for line in claim["lines"]] == [None, None, 2]
    assert [line["amount"] for line in claim["lines"]] == ["50.00", "30.00", "400.00"]


def test_ids_increase_with_each_submission(client):
    first = client.post("/claims", json=CONTRACT_BODY).json()["id"]
    second = client.post("/claims", json=CONTRACT_BODY).json()["id"]

    assert second > first


def test_currency_is_upper_cased(client):
    response = client.post("/claims", json=body_with(lambda b: b["lines"][0].update(currency=" eur")))

    assert response.status_code == 201
    assert response.json()["lines"][0]["currency"] == "EUR"


def test_lodging_nights_default_to_one(client):
    response = client.post("/claims", json=body_with(lambda b: b["lines"][2].pop("nights")))

    assert response.status_code == 201
    assert response.json()["lines"][2]["nights"] == 1


def test_unsupported_currency_is_accepted(client):
    # spec FR-013: found at check time, not refused at submission.
    response = client.post("/claims", json=body_with(lambda b: b["lines"][0].update(currency="JPY")))

    assert response.status_code == 201
    assert response.json()["lines"][0]["currency"] == "JPY"


def test_stored_claim_matches_the_response(client, db_path):
    created = client.post("/claims", json=CONTRACT_BODY).json()

    conn = store.connect(db_path)
    try:
        stored = store.get_claim(conn, created["id"])
    finally:
        conn.close()
    assert stored.model_dump(mode="json") == created


@pytest.mark.parametrize(
    ("change", "loc"),
    [
        (lambda b: b["trip"].update(end_date="2026-03-09"), ["body", "trip", "end_date"]),
        (lambda b: b["lines"][1].update(category="food"), ["body", "lines", 1, "category"]),
        (lambda b: b["lines"][1].update(amount="0.00"), ["body", "lines", 1, "amount"]),
        (lambda b: b["lines"][1].update(amount=30.0), ["body", "lines", 1, "amount"]),
        (lambda b: b["lines"][1].update(merchant=""), ["body", "lines", 1, "merchant"]),
        (lambda b: b["lines"][1].update(date="2026-03-20"), ["body", "lines", 1, "date"]),
        (lambda b: b["lines"][0].update(nights=1), ["body", "lines", 0, "nights"]),
        (lambda b: b.update(lines=[]), ["body", "lines"]),
    ],
)
def test_invalid_claim_is_refused_and_nothing_is_stored(client, db_path, change, loc):
    before = claim_count(db_path)

    response = client.post("/claims", json=body_with(change))

    assert response.status_code == 422
    assert loc in [error["loc"] for error in response.json()["detail"]]
    assert claim_count(db_path) == before


@pytest.mark.parametrize(
    ("change", "loc"),
    [
        # S2 (M03 AI review): a huge amount was stored, then crashed the check with a 500.
        (lambda b: b["lines"][1].update(amount="1" + "0" * 30 + ".00"),
         ["body", "lines", 1, "amount"]),
        # P2: "1e2" was stored and echoed as "1E+2".
        (lambda b: b["lines"][1].update(amount="1e2"), ["body", "lines", 1, "amount"]),
        # S3: a trip to 9999-12-31 with 2,900,000 nights made every check take seconds.
        (lambda b: (b["trip"].update(end_date="9999-12-31"),
                    b["lines"][2].update(nights=2_900_000)),
         ["body", "trip", "end_date"]),
        (lambda b: b.update(lines=[b["lines"][0]] * 51), ["body", "lines"]),
        (lambda b: b.update(employee_id="E" * 201), ["body", "employee_id"]),
    ],
)
def test_m06_attack_is_refused_and_nothing_is_stored(client, db_path, change, loc):
    response = client.post("/claims", json=body_with(change))

    assert response.status_code == 422
    assert loc in [error["loc"] for error in response.json()["detail"]]
    assert claim_count(db_path) == 0


def test_employee_id_is_trimmed(client):  # S4
    response = client.post("/claims", json=body_with(lambda b: b.update(employee_id=" E-7 ")))

    assert response.status_code == 201
    assert response.json()["employee_id"] == "E-7"


def test_every_field_error_is_listed(client, db_path):
    def change(b):
        b["employee_id"] = ""
        b["lines"][0]["amount"] = "-1"
        b["lines"][2]["category"] = "spa"

    response = client.post("/claims", json=body_with(change))

    assert response.status_code == 422
    locs = [error["loc"] for error in response.json()["detail"]]
    assert ["body", "employee_id"] in locs
    assert ["body", "lines", 0, "amount"] in locs
    assert ["body", "lines", 2, "category"] in locs
    assert claim_count(db_path) == 0
