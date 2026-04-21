"""Integration tests for the HTTP surface.

We focus on the behaviours that are easy to get subtly wrong: idempotent
writes, money precision, filter/sort correctness, and input validation.
"""
from __future__ import annotations

from datetime import date, timedelta


def _sample(**overrides):
    payload = {
        "amount": "199.50",
        "category": "Food & Dining",
        "description": "Lunch",
        "date": date.today().isoformat(),
    }
    payload.update(overrides)
    return payload


def test_create_and_list_expense(client):
    r = client.post("/expenses", json=_sample(), headers={"Idempotency-Key": "abcdef1234"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["amount"] == "199.50"
    assert body["category"] == "Food & Dining"

    r = client.get("/expenses")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["total"] == "199.50"


def test_idempotent_retry_does_not_duplicate(client):
    key = "idemp-test-0001"
    r1 = client.post("/expenses", json=_sample(), headers={"Idempotency-Key": key})
    r2 = client.post("/expenses", json=_sample(), headers={"Idempotency-Key": key})
    assert r1.status_code == 201
    assert r2.status_code == 200  # replay
    assert r1.json()["id"] == r2.json()["id"]

    list_resp = client.get("/expenses").json()
    assert list_resp["count"] == 1


def test_money_precision_is_preserved(client):
    # Three entries whose naive float sum drifts (0.1 + 0.2 + 0.3).
    for amt in ["0.10", "0.20", "0.30"]:
        r = client.post(
            "/expenses",
            json=_sample(amount=amt, description=f"item-{amt}"),
            headers={"Idempotency-Key": f"key-{amt}-xyz"},
        )
        assert r.status_code == 201
    total = client.get("/expenses").json()["total"]
    assert total == "0.60"


def test_rejects_negative_amount(client):
    r = client.post("/expenses", json=_sample(amount="-1.00"))
    assert r.status_code == 422


def test_rejects_too_many_decimals(client):
    r = client.post("/expenses", json=_sample(amount="1.234"))
    assert r.status_code == 422


def test_rejects_future_date(client):
    future = (date.today() + timedelta(days=1)).isoformat()
    r = client.post("/expenses", json=_sample(date=future))
    assert r.status_code == 422


def test_rejects_unknown_category(client):
    r = client.post("/expenses", json=_sample(category="Crypto"))
    assert r.status_code == 422


def test_filter_by_category(client):
    client.post(
        "/expenses",
        json=_sample(category="Food & Dining", description="a"),
        headers={"Idempotency-Key": "key-aaaa-1"},
    )
    client.post(
        "/expenses",
        json=_sample(category="Transport", description="b"),
        headers={"Idempotency-Key": "key-bbbb-2"},
    )
    only_transport = client.get("/expenses", params={"category": "Transport"}).json()
    assert only_transport["count"] == 1
    assert only_transport["expenses"][0]["category"] == "Transport"


def test_sort_date_desc(client):
    today = date.today()
    yesterday = today - timedelta(days=1)
    client.post(
        "/expenses",
        json=_sample(date=yesterday.isoformat(), description="older"),
        headers={"Idempotency-Key": "sort-1-older"},
    )
    client.post(
        "/expenses",
        json=_sample(date=today.isoformat(), description="newer"),
        headers={"Idempotency-Key": "sort-2-newer"},
    )
    items = client.get("/expenses", params={"sort": "date_desc"}).json()["expenses"]
    assert items[0]["description"] == "newer"
    assert items[1]["description"] == "older"


def test_sort_date_asc(client):
    today = date.today()
    yesterday = today - timedelta(days=1)
    client.post(
        "/expenses",
        json=_sample(date=today.isoformat(), description="newer"),
        headers={"Idempotency-Key": "sort-asc-1-newer"},
    )
    client.post(
        "/expenses",
        json=_sample(date=yesterday.isoformat(), description="older"),
        headers={"Idempotency-Key": "sort-asc-2-older"},
    )
    items = client.get("/expenses", params={"sort": "date_asc"}).json()["expenses"]
    assert items[0]["description"] == "older"
    assert items[1]["description"] == "newer"


def test_rejects_unknown_sort(client):
    r = client.get("/expenses", params={"sort": "amount_asc"})
    assert r.status_code == 400
