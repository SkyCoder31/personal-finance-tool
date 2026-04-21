"""SQLAlchemy engine, session factory, and ORM model.

We store money as BIGINT paise (the smallest INR unit). Storing rupees as
FLOAT/REAL would silently corrupt sums (0.1 + 0.2 != 0.3). Integer paise
is exact, supported everywhere, and trivially converted at the boundary.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Index,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.config import DATABASE_URL

# check_same_thread=False is needed because FastAPI uses a threadpool for
# sync endpoints; SQLAlchemy's session is still per-request so this is safe.
_connect_args = (
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(String(36), primary_key=True)  # UUIDv4
    amount_paise = Column(BigInteger, nullable=False)
    category = Column(String(50), nullable=False)
    description = Column(String(500), nullable=False)
    date = Column(Date, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    # Nullable so requests without the header still work; UNIQUE so replay
    # attempts with a reused key short-circuit at the DB level.
    idempotency_key = Column(String(128), unique=True, nullable=True)

    __table_args__ = (
        Index("ix_expenses_category", "category"),
        Index("ix_expenses_date", "date"),
    )


def init_db() -> None:
    """Create tables if they don't yet exist. Idempotent."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency — yields a scoped session and guarantees cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
