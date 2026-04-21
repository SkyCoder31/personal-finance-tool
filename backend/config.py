"""Application configuration.

Single source of truth for environment-driven settings. Centralising this
avoids scattering os.getenv calls across the codebase and makes tests
easier (monkeypatch one place).
"""
from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL: str = os.getenv(
    "DATABASE_URL", f"sqlite:///{DATA_DIR.as_posix()}/expenses.db"
)

API_BASE_URL: str = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

# A closed category list prevents typos from fragmenting the data set
# (e.g. "Food", "food", "FOOD"). If new categories are needed, add here.
ALLOWED_CATEGORIES: list[str] = [
    "Food & Dining",
    "Groceries",
    "Transport",
    "Shopping",
    "Entertainment",
    "Bills & Utilities",
    "Health",
    "Travel",
    "Education",
    "Other",
]

# Sanity ceiling on a single expense: 10 crore rupees, in paise.
MAX_AMOUNT_PAISE: int = 10_00_00_000_00

# Allowed sort tokens (kept explicit to reject arbitrary user input).
ALLOWED_SORTS: set[str] = {"date_desc", "date_asc"}
