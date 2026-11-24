"""SQLite persistence for claims (data-model.md Storage).

Money is stored as TEXT holding str(Decimal), never REAL. Claim IDs come from AUTOINCREMENT,
so a higher ID means a later submission (research R-03).
"""

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from agentic_app.schemas import Claim, ClaimIn, ExpenseLine, ExpenseLineIn, PriorLine, Trip

_SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id TEXT NOT NULL,
    city        TEXT NOT NULL,
    start_date  TEXT NOT NULL,
    end_date    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS expense_lines (
    claim_id         INTEGER NOT NULL REFERENCES claims(id),
    line_no          INTEGER NOT NULL,
    date             TEXT NOT NULL,
    category         TEXT NOT NULL,
    merchant         TEXT NOT NULL,
    amount           TEXT NOT NULL,
    currency         TEXT NOT NULL,
    receipt_attached INTEGER NOT NULL,
    nights           INTEGER,
    PRIMARY KEY (claim_id, line_no)
);
CREATE INDEX IF NOT EXISTS claims_by_employee ON claims (employee_id, id);
"""

_LINE_COLUMNS = "line_no, date, category, merchant, amount, currency, receipt_attached, nights"


def connect(db_path: Path) -> sqlite3.Connection:
    # One connection per request, never shared; FastAPI may open and use it on different
    # threadpool threads, so the same-thread check is turned off.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)


def _insert_line(conn: sqlite3.Connection, claim_id: int, line_no: int, line: ExpenseLineIn) -> None:
    conn.execute(
        f"INSERT INTO expense_lines (claim_id, {_LINE_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            claim_id, line_no, line.date.isoformat(), line.category.value, line.merchant,
            str(line.amount), line.currency, int(line.receipt_attached), line.nights,
        ),
    )


def add_claim(conn: sqlite3.Connection, claim_in: ClaimIn) -> Claim:
    """Store a claim and its lines in one transaction; nothing is kept if any insert fails."""
    with conn:
        cursor = conn.execute(
            "INSERT INTO claims (employee_id, city, start_date, end_date) VALUES (?, ?, ?, ?)",
            (
                claim_in.employee_id, claim_in.trip.destination_city,
                claim_in.trip.start_date.isoformat(), claim_in.trip.end_date.isoformat(),
            ),
        )
        claim_id = cursor.lastrowid
        for line_no, line in enumerate(claim_in.lines, start=1):
            _insert_line(conn, claim_id, line_no, line)
    return Claim(
        id=claim_id,
        employee_id=claim_in.employee_id,
        trip=claim_in.trip,
        lines=[
            ExpenseLine(line_no=line_no, **line.model_dump())
            for line_no, line in enumerate(claim_in.lines, start=1)
        ],
    )


def _line_from_row(row: tuple) -> ExpenseLine:
    line_no, line_date, category, merchant, amount, currency, receipt_attached, nights = row
    return ExpenseLine(
        line_no=line_no, date=date.fromisoformat(line_date), category=category,
        merchant=merchant, amount=Decimal(amount), currency=currency,
        receipt_attached=bool(receipt_attached), nights=nights,
    )


def get_claim(conn: sqlite3.Connection, claim_id: int) -> Claim | None:
    row = conn.execute(
        "SELECT id, employee_id, city, start_date, end_date FROM claims WHERE id = ?", (claim_id,)
    ).fetchone()
    if row is None:
        return None
    _, employee_id, city, start_date, end_date = row
    lines = conn.execute(
        f"SELECT {_LINE_COLUMNS} FROM expense_lines WHERE claim_id = ? ORDER BY line_no",
        (claim_id,),
    ).fetchall()
    return Claim(
        id=claim_id,
        employee_id=employee_id,
        trip=Trip(
            destination_city=city,
            start_date=date.fromisoformat(start_date),
            end_date=date.fromisoformat(end_date),
        ),
        lines=[_line_from_row(line) for line in lines],
    )


def prior_lines(
    conn: sqlite3.Connection, employee_id: str, before_claim_id: int
) -> list[PriorLine]:
    """Lines of the employee's claims submitted before `before_claim_id` (research R-11)."""
    rows = conn.execute(
        """
        SELECT l.claim_id, l.line_no, l.date, l.amount, l.currency, l.merchant
        FROM expense_lines AS l JOIN claims AS c ON c.id = l.claim_id
        WHERE c.employee_id = ? AND c.id < ?
        ORDER BY l.claim_id, l.line_no
        """,
        (employee_id, before_claim_id),
    ).fetchall()
    return [
        PriorLine(
            claim_id=claim_id, line_no=line_no, date=date.fromisoformat(line_date),
            amount=Decimal(amount), currency=currency, merchant=merchant,
        )
        for claim_id, line_no, line_date, amount, currency, merchant in rows
    ]


def list_claims(conn: sqlite3.Connection, employee_id: str) -> list[Claim]:
    """An employee's claims in submission order (ascending ID)."""
    ids = conn.execute(
        "SELECT id FROM claims WHERE employee_id = ? ORDER BY id", (employee_id,)
    ).fetchall()
    return [get_claim(conn, claim_id) for (claim_id,) in ids]
