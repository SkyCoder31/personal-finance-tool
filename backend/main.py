"""FastAPI application — the /expenses REST API.

Design notes:
* Idempotency-Key is optional but strongly recommended. When present, a
  replay returns HTTP 200 (instead of 201) so clients can tell the write
  did not happen twice.
* Validation errors come back as 422 (Pydantic default). Business errors
  such as an unknown `sort` value return 400 with a clear message.
* A catch-all exception handler ensures we never leak stack traces to the
  client; full details go to the server log.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.config import ALLOWED_SORTS
from backend.database import get_db, init_db
from backend.models import ExpenseCreate, ExpenseList, ExpenseResponse
from backend.repository import ExpenseRepository

log = logging.getLogger("fenmo.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Fenmo Expense Tracker API",
    version="1.0.0",
    description="Minimal personal-finance API. Safe for retries.",
    lifespan=lifespan,
)

# Permissive CORS is fine for this exercise — the frontend and backend are
# co-located. In real production we'd pin this to known frontend origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unhandled(_, exc: Exception):
    log.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "Something went wrong."},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/expenses", response_model=ExpenseResponse, status_code=201)
def create_expense(
    payload: ExpenseCreate,
    response: Response,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description="Client-generated UUID to make retries safe.",
    ),
    db: Session = Depends(get_db),
):
    if idempotency_key is not None:
        if not (8 <= len(idempotency_key) <= 128):
            raise HTTPException(
                status_code=400,
                detail="Idempotency-Key must be 8-128 characters",
            )
    repo = ExpenseRepository(db)
    expense, created = repo.create_with_idempotency(payload, idempotency_key)
    if not created:
        # Replay: the record already existed under this key.
        response.status_code = 200
    return expense


@app.get("/expenses", response_model=ExpenseList)
def list_expenses(
    category: str | None = None,
    sort: str | None = None,
    db: Session = Depends(get_db),
):
    if sort is not None and sort not in ALLOWED_SORTS:
        raise HTTPException(
            status_code=400,
            detail=f"sort must be one of: {', '.join(sorted(ALLOWED_SORTS))}",
        )
    repo = ExpenseRepository(db)
    expenses = repo.list(category=category, sort=sort or "date_desc")
    total = sum((e["amount"] for e in expenses), Decimal("0"))
    return {"expenses": expenses, "total": total, "count": len(expenses)}
