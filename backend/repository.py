"""Data access layer.

Keeping persistence isolated from the HTTP layer means the API handlers
stay small, the business rules (idempotency, unit conversion) live in one
place, and the backend is easier to test.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import Expense
from backend.models import ExpenseCreate


def paise_to_rupees(paise: int) -> Decimal:
    return (Decimal(paise) / Decimal(100)).quantize(Decimal("0.01"))


def rupees_to_paise(rupees: Decimal) -> int:
    return int((rupees * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _to_dict(e: Expense) -> dict:
    return {
        "id": e.id,
        "amount": paise_to_rupees(e.amount_paise),
        "category": e.category,
        "description": e.description,
        "date": e.date,
        "created_at": e.created_at,
    }


class ExpenseRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_with_idempotency(
        self, data: ExpenseCreate, idempotency_key: str | None
    ) -> tuple[dict, bool]:
        """Insert an expense, honouring idempotency.

        Returns (expense_dict, created). `created=False` indicates a replay:
        a request with this same Idempotency-Key was already processed, so
        we return the original record without inserting a duplicate.

        We handle the race where two concurrent requests share a key by
        catching the unique-constraint IntegrityError and re-fetching.
        """
        if idempotency_key:
            existing = (
                self.db.query(Expense)
                .filter(Expense.idempotency_key == idempotency_key)
                .first()
            )
            if existing:
                return _to_dict(existing), False

        record = Expense(
            id=str(uuid.uuid4()),
            amount_paise=rupees_to_paise(data.amount),
            category=data.category,
            description=data.description,
            date=data.date,
            created_at=datetime.now(timezone.utc),
            idempotency_key=idempotency_key,
        )
        self.db.add(record)
        try:
            self.db.commit()
        except IntegrityError:
            # Concurrent writer beat us to the unique key — resolve by
            # returning their row so the caller's POST is still idempotent.
            self.db.rollback()
            existing = (
                self.db.query(Expense)
                .filter(Expense.idempotency_key == idempotency_key)
                .first()
            )
            if existing:
                return _to_dict(existing), False
            raise
        self.db.refresh(record)
        return _to_dict(record), True

    def list(
        self, *, category: str | None = None, sort: str = "date_desc"
    ) -> list[dict]:
        q = self.db.query(Expense)
        if category:
            q = q.filter(Expense.category == category)
        # Secondary sort on created_at breaks ties so same-day entries
        # appear in insertion order (newest first).
        if sort == "date_desc":
            q = q.order_by(desc(Expense.date), desc(Expense.created_at))
        return [_to_dict(e) for e in q.all()]
