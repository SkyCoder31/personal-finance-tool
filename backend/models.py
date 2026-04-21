"""Pydantic schemas for request/response validation.

Amount crosses the wire as a string-serialised Decimal (JSON numbers can
lose precision when large or fractional). Pydantic parses strings into
Decimal cleanly, and the repository converts to integer paise for storage.
"""
from __future__ import annotations

from datetime import date as _date
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.config import ALLOWED_CATEGORIES, MAX_AMOUNT_PAISE

_TWO_PLACES = Decimal("0.01")


class ExpenseCreate(BaseModel):
    amount: Decimal = Field(..., description="INR amount with up to 2 decimal places")
    category: str = Field(..., min_length=1, max_length=50)
    description: str = Field(..., min_length=1, max_length=500)
    date: _date

    @field_validator("amount", mode="before")
    @classmethod
    def _coerce_amount(cls, v):
        # Strings are the recommended input; reject NaN / infinity.
        try:
            d = Decimal(str(v))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Amount is not a valid number") from exc
        if not d.is_finite():
            raise ValueError("Amount must be a finite number")
        return d

    @field_validator("amount")
    @classmethod
    def _validate_amount(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0"):
            raise ValueError("Amount must be greater than zero")
        # Reject precision beyond paise rather than silently rounding:
        # better to make the user confirm than to lose their money.
        if v != v.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP):
            raise ValueError("Amount cannot have more than 2 decimal places")
        paise = int((v * 100).to_integral_value(rounding=ROUND_HALF_UP))
        if paise > MAX_AMOUNT_PAISE:
            raise ValueError("Amount exceeds the maximum allowed value")
        return v

    @field_validator("category")
    @classmethod
    def _validate_category(cls, v: str) -> str:
        v = v.strip()
        if v not in ALLOWED_CATEGORIES:
            raise ValueError(
                "Category must be one of: " + ", ".join(ALLOWED_CATEGORIES)
            )
        return v

    @field_validator("description")
    @classmethod
    def _validate_description(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Description is required")
        return v

    @field_validator("date")
    @classmethod
    def _validate_date(cls, v: _date) -> _date:
        if v > _date.today():
            raise ValueError("Date cannot be in the future")
        return v


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    amount: Decimal
    category: str
    description: str
    date: _date
    created_at: datetime


class ExpenseList(BaseModel):
    expenses: list[ExpenseResponse]
    total: Decimal
    count: int
