"""Streamlit UI for the Expense Tracker.

Deployment model:
* Streamlit Community Cloud runs this file as the entrypoint.
* We spin up the FastAPI backend in a daemon thread on first import so
  the whole app ships in a single container. The UI then talks to
  127.0.0.1:8000 like any other HTTP client.
* Setting EMBEDDED_BACKEND=0 disables the in-process backend — useful
  if you deploy the API separately (e.g., Render) and point Streamlit
  at it via API_BASE_URL.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Make the repo root importable regardless of how streamlit is launched.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _start_embedded_backend() -> None:
    """Run FastAPI in-process so Streamlit Cloud can host the full stack."""
    if os.environ.get("EMBEDDED_BACKEND", "1") != "1":
        return
    if os.environ.get("_FENMO_BACKEND_STARTED") == "1":
        return
    os.environ["_FENMO_BACKEND_STARTED"] = "1"

    import uvicorn

    from backend.main import app as backend_app

    def _run():
        uvicorn.run(
            backend_app,
            host="127.0.0.1",
            port=8000,
            log_level="warning",
            access_log=False,
        )

    thread = threading.Thread(target=_run, daemon=True, name="fenmo-backend")
    thread.start()

    # Wait briefly for the socket to start accepting connections so the
    # first page load doesn't hit a connection-refused error.
    import socket

    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", 8000), timeout=0.1):
                break
        except OSError:
            time.sleep(0.1)


_start_embedded_backend()


import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from backend.config import ALLOWED_CATEGORIES  # noqa: E402
from frontend.api_client import ExpenseAPIError, get_client  # noqa: E402


st.set_page_config(
    page_title="Fenmo Expense Tracker",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .stMetric { background: #f7f8fa; padding: 0.8rem 1rem; border-radius: 10px; }
      div[data-testid="stForm"] { background: #fafbfc; padding: 1rem; border-radius: 12px;
                                  border: 1px solid #eef0f3; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state() -> None:
    # The idempotency key is generated once per "draft" expense. It is
    # rotated only after a successful submission, so accidental double-
    # clicks during a slow request still share a key (the backend
    # deduplicates). A page refresh mid-submit rotates the key, which
    # is what we want — the refresh is a new logical attempt.
    if "idempotency_key" not in st.session_state:
        st.session_state.idempotency_key = str(uuid.uuid4())
    if "flash" not in st.session_state:
        st.session_state.flash = None


_init_state()
client = get_client()


def _rotate_key() -> None:
    st.session_state.idempotency_key = str(uuid.uuid4())


st.title("💸 Fenmo Expense Tracker")
st.caption("Record and review your personal expenses.")

if st.session_state.flash:
    kind, msg = st.session_state.flash
    {"success": st.success, "error": st.error, "info": st.info}.get(kind, st.info)(msg)
    st.session_state.flash = None


form_col, list_col = st.columns([1, 2], gap="large")

with form_col:
    st.subheader("Add expense")
    with st.form("add_expense_form", clear_on_submit=True):
        raw_amount = st.text_input(
            "Amount (₹)",
            placeholder="e.g. 499.00",
            help="Up to 2 decimal places. Must be greater than zero.",
        )
        category = st.selectbox("Category", options=ALLOWED_CATEGORIES, index=0)
        description = st.text_input(
            "Description",
            max_chars=200,
            placeholder="e.g. Dinner with friends",
        )
        expense_date = st.date_input(
            "Date",
            value=pd.Timestamp.today().date(),
            max_value=pd.Timestamp.today().date(),
        )
        submitted = st.form_submit_button(
            "Add expense", use_container_width=True, type="primary"
        )

    if submitted:
        errors: list[str] = []
        amount_value: Decimal | None = None
        try:
            amount_value = Decimal((raw_amount or "").strip())
        except InvalidOperation:
            errors.append("Amount must be a valid number.")
        else:
            if amount_value <= Decimal("0"):
                errors.append("Amount must be greater than zero.")
            elif amount_value != amount_value.quantize(Decimal("0.01")):
                errors.append("Amount can have at most 2 decimal places.")

        if not description.strip():
            errors.append("Description is required.")
        if not expense_date:
            errors.append("Date is required.")

        if errors:
            for msg in errors:
                st.error(msg)
        else:
            try:
                with st.spinner("Saving..."):
                    result = client.create_expense(
                        amount=amount_value,
                        category=category,
                        description=description.strip(),
                        date=expense_date.isoformat(),
                        idempotency_key=st.session_state.idempotency_key,
                    )
                _rotate_key()
                st.session_state.flash = (
                    "success",
                    f"Added ₹{Decimal(str(result['amount'])):,.2f} to {result['category']}.",
                )
                st.rerun()
            except ExpenseAPIError as exc:
                st.error(f"Could not add expense: {exc}")
            except Exception as exc:  # defensive — surface unexpected errors
                st.error(f"Unexpected error: {exc}")


with list_col:
    st.subheader("Your expenses")

    f1, f2, f3 = st.columns([2, 2, 1])
    with f1:
        filter_category = st.selectbox(
            "Filter by category",
            options=["All"] + ALLOWED_CATEGORIES,
            index=0,
            key="filter_category",
        )
    with f2:
        st.selectbox(
            "Sort by", options=["Newest first"], index=0, key="sort_choice"
        )
    with f3:
        st.markdown("&nbsp;", unsafe_allow_html=True)
        if st.button("Refresh", use_container_width=True):
            st.rerun()

    load_error: str | None = None
    try:
        with st.spinner("Loading expenses..."):
            data = client.list_expenses(
                category=None if filter_category == "All" else filter_category,
                sort="date_desc",
            )
    except ExpenseAPIError as exc:
        load_error = str(exc)
        data = {"expenses": [], "total": "0", "count": 0}

    if load_error:
        st.error(f"Failed to load expenses: {load_error}")

    expenses = data.get("expenses", [])
    total = Decimal(str(data.get("total", "0")))

    m1, m2 = st.columns(2)
    m1.metric("Total (visible)", f"₹{total:,.2f}")
    m2.metric("Entries (visible)", f"{data.get('count', 0)}")

    if not expenses:
        st.info("No expenses to show. Add your first one on the left.")
    else:
        df = pd.DataFrame(expenses)
        df["amount_num"] = df["amount"].map(lambda v: Decimal(str(v)))
        df_display = pd.DataFrame(
            {
                "Date": df["date"],
                "Category": df["category"],
                "Description": df["description"],
                "Amount": df["amount_num"].map(lambda v: f"₹{v:,.2f}"),
            }
        )
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        with st.expander("Totals by category"):
            by_cat = (
                df.groupby("category", as_index=False)["amount_num"]
                .sum()
                .sort_values("amount_num", ascending=False)
            )
            by_cat_display = pd.DataFrame(
                {
                    "Category": by_cat["category"],
                    "Total": by_cat["amount_num"].map(lambda v: f"₹{v:,.2f}"),
                }
            )
            st.dataframe(by_cat_display, use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "Built for Fenmo. Backend: FastAPI + SQLite. "
    "Frontend: Streamlit. All amounts are stored as integer paise for exactness."
)
