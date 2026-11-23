"""AC-023..AC-031: HTTP contract of the microservice (FastAPI TestClient, no network)."""
from __future__ import annotations

import pytest


def _post(client, **body):
    return client.post("/v1/check", json=body)


def _exhaust(client, client_id="alice", tier="free", count=5):
    return [_post(client, client_id=client_id, tier=tier) for _ in range(count)]


def test_ac_023_allowed_response_has_body_and_ratelimit_headers(client):
    resp = _post(client, client_id="alice", tier="free")
    assert resp.status_code == 200, f"expected: 200 | observed: {resp.status_code} {resp.text}"
    assert resp.headers["content-type"].startswith("application/json")
    expected_body = {"allowed": True, "limit": 5, "remaining": 4, "retry_after": 0, "reset": 1}
    assert resp.json() == expected_body, f"expected: {expected_body} | observed: {resp.json()}"
    assert resp.headers["x-ratelimit-limit"] == "5"
    assert resp.headers["x-ratelimit-remaining"] == "4"
    assert resp.headers["x-ratelimit-reset"] == "1"
    assert "retry-after" not in resp.headers


def test_ac_024_denied_response_is_429_with_retry_after(client):
    _exhaust(client)
    resp = _post(client, client_id="alice", tier="free")
    assert resp.status_code == 429, f"expected: 429 | observed: {resp.status_code} {resp.text}"
    expected_body = {
        "allowed": False, "error": "rate_limited", "limit": 5,
        "remaining": 0, "retry_after": 1, "reset": 5,
    }
    assert resp.json() == expected_body, f"expected: {expected_body} | observed: {resp.json()}"
    assert resp.headers["retry-after"] == "1"
    assert resp.headers["x-ratelimit-limit"] == "5"
    assert resp.headers["x-ratelimit-remaining"] == "0"
    assert resp.headers["x-ratelimit-reset"] == "5"


def test_ac_025_cost_defaults_to_one_and_can_be_set(client):
    assert _post(client, client_id="alice", tier="free").json()["remaining"] == 4
    assert _post(client, client_id="alice", tier="free", cost=2).json()["remaining"] == 2


def test_ac_026_unknown_tier_and_oversized_cost_are_400(client):
    unknown = _post(client, client_id="alice", tier="gold")
    assert (unknown.status_code, unknown.json()) == (400, {"error": "unknown_tier"})
    too_big = _post(client, client_id="alice", tier="free", cost=6)
    assert (too_big.status_code, too_big.json()) == (400, {"error": "cost_exceeds_capacity"})


INVALID_BODIES = [
    {},
    {"tier": "free"},
    {"client_id": "alice"},
    {"client_id": "", "tier": "free"},
    {"client_id": "bad id", "tier": "free"},
    {"client_id": "x" * 129, "tier": "free"},
    {"client_id": 123, "tier": "free"},
    {"client_id": "alice", "tier": ""},
    {"client_id": "alice", "tier": "free", "cost": 0},
    {"client_id": "alice", "tier": "free", "cost": -1},
    {"client_id": "alice", "tier": "free", "cost": "x"},
    {"client_id": "alice", "tier": "free", "cost": 1.5},
    {"client_id": "alice", "tier": "free", "cost": True},
    {"client_id": "alice", "tier": "free", "extra": 1},
]


@pytest.mark.parametrize("body", INVALID_BODIES)
def test_ac_027_invalid_payloads_are_422(client, body):
    resp = client.post("/v1/check", json=body)
    assert resp.status_code == 422, f"expected: 422 | observed: {resp.status_code} for {body}"


def test_ac_027_malformed_and_non_object_json_are_422(client):
    headers = {"content-type": "application/json"}
    assert client.post("/v1/check", content="{not json", headers=headers).status_code == 422
    assert client.post("/v1/check", content="[]", headers=headers).status_code == 422


def test_ac_028_health_endpoint(client):
    resp = client.get("/health")
    assert (resp.status_code, resp.json()) == (200, {"status": "ok"})


def test_ac_029_http_layer_uses_the_injected_clock(client, clock):
    _exhaust(client)
    denied = _post(client, client_id="alice", tier="free")
    assert denied.status_code == 429
    clock.advance(int(denied.headers["retry-after"]))
    assert _post(client, client_id="alice", tier="free").status_code == 200


def test_ac_030_error_responses_never_leak_internals(client):
    _exhaust(client)
    responses = [
        _post(client, client_id="alice", tier="free"),
        _post(client, client_id="alice", tier="gold"),
        _post(client, client_id="", tier="free"),
        client.get("/no-such-route"),
    ]
    for resp in responses:
        assert "Traceback" not in resp.text, f"stack trace leaked on {resp.status_code}"
        assert ".py" not in resp.text, f"source path leaked on {resp.status_code}: {resp.text}"


def test_ac_031_wrong_method_is_405(client):
    assert client.get("/v1/check").status_code == 405
