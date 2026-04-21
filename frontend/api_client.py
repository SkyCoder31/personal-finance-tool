"""HTTP client that wraps the Expense Tracker API.

Key behaviours:
* Automatic retry with exponential backoff on 5xx/connection errors.
  Retrying POST is normally unsafe, but we always send Idempotency-Key,
  so the backend deduplicates automatically.
* A timeout is always set — a slow backend must never hang the UI.
* Errors are translated into a single exception type the UI can catch.
"""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_TIMEOUT_SECONDS = 10.0


class ExpenseAPIError(Exception):
    def __init__(self, message: str, *, status: Optional[int] = None, details: Any = None):
        super().__init__(message)
        self.status = status
        self.details = details


class APIClient:
    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.5,  # 0.5s, 1s, 2s
            status_forcelist=(502, 503, 504),
            # POST is normally excluded from retries; safe here thanks to
            # Idempotency-Key on every create call.
            allowed_methods=frozenset({"GET", "POST"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _decode(self, r: requests.Response) -> dict:
        if r.status_code >= 400:
            msg: str
            details: Any = None
            try:
                payload = r.json()
                details = payload
                msg = payload.get("detail") or payload.get("message") or r.text
                if isinstance(msg, list):
                    # FastAPI validation errors come back as a list of dicts
                    msg = "; ".join(
                        f"{'.'.join(str(p) for p in e.get('loc', [])[-1:])}: {e.get('msg')}"
                        for e in msg
                    )
            except ValueError:
                msg = r.text or f"HTTP {r.status_code}"
            raise ExpenseAPIError(str(msg), status=r.status_code, details=details)
        if not r.content:
            return {}
        return r.json()

    def create_expense(
        self,
        *,
        amount: Decimal,
        category: str,
        description: str,
        date: str,
        idempotency_key: str,
    ) -> dict:
        headers = {"Idempotency-Key": idempotency_key}
        payload = {
            "amount": str(amount),  # Decimal over the wire as a string
            "category": category,
            "description": description,
            "date": date,
        }
        try:
            r = self.session.post(
                f"{self.base_url}/expenses",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise ExpenseAPIError(
                "Could not reach the API. Check your connection and try again."
            ) from exc
        return self._decode(r)

    def list_expenses(
        self, *, category: Optional[str] = None, sort: str = "date_desc"
    ) -> dict:
        params: dict[str, Any] = {"sort": sort}
        if category:
            params["category"] = category
        try:
            r = self.session.get(
                f"{self.base_url}/expenses", params=params, timeout=self.timeout
            )
        except requests.exceptions.RequestException as exc:
            raise ExpenseAPIError(
                "Could not reach the API. Check your connection and try again."
            ) from exc
        return self._decode(r)


def get_client() -> APIClient:
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    return APIClient(base_url=base_url)
