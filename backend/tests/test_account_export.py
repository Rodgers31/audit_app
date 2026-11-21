"""Run the registered export route with synthetic provider users and subscriptions."""

from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

import supabase_auth
from models import NewsletterSubscriber, User


FIRST = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SECOND = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
CREATED = "2025-04-01T04:17:00Z"
ENDPOINT = "/api/v1/user/export"
EMAILS = {FIRST: "Wanjiku@example.test", SECOND: "Musa@example.test"}


def authorization(account):
    return {"Authorization": f"Bearer {account}"}


@pytest.fixture
def provider(client, db_session, monkeypatch):
    state = SimpleNamespace(requests=[], wrong_owner=False, missing_user=False,
                            fail_alerts=False, unverified=False)
    db_session.add_all([
        NewsletterSubscriber(email=EMAILS[FIRST].lower(), confirmed=True),
        NewsletterSubscriber(
            email=EMAILS[SECOND].lower(), confirmed=True,
            unsubscribed_at=datetime(2025, 9, 12, tzinfo=timezone.utc),
        ),
    ])
    db_session.flush()

    def claims(token):
        if token not in EMAILS:
            raise HTTPException(401, "Invalid token")
        # The provider, rather than this potentially stale claim, owns the email.
        return {"sub": token, "email": EMAILS[SECOND]}

    def respond(request):
        state.requests.append(request)
        assert request.method == "GET"
        assert request.url.host == "account-export.test"
        path, query = request.url.path, request.url.params
        if path.startswith("/auth/v1/admin/users/"):
            owner = path.rsplit("/", 1)[-1]
            if state.missing_user:
                return httpx.Response(404, json={"message": "private-provider-response"})
            return httpx.Response(200, json={
                "id": owner, "email": EMAILS[owner], "created_at": CREATED,
                "email_confirmed_at": None if state.unverified else CREATED,
                "user_metadata": {"terms_accepted_at": CREATED},
            })
        if path == "/rest/v1/profiles":
            owner = query["id"].removeprefix("eq.")
            return httpx.Response(200, json=[{
                "id": owner, "roles": ["citizen"], "display_name": EMAILS[owner].split("@")[0],
                "email": EMAILS[SECOND], "created_at": CREATED,
            }])
        owner = query["user_id"].removeprefix("eq.")
        assert owner in EMAILS and query["order"] == "id.asc" and query["limit"] == "500"
        start = int(query["id"].removeprefix("gt."))
        if path == "/rest/v1/watchlist_items":
            amount = 2 if owner == FIRST else 1
            if start >= amount:
                return httpx.Response(200, json=[])
            # Simulate a provider limit smaller than the requested page.
            return httpx.Response(200, json=[{
                "id": start + 1, "user_id": SECOND if state.wrong_owner else owner,
                "item_type": "county", "item_id": "baringo" if owner == FIRST else "kitui",
                "label": "Baringo County" if owner == FIRST else "Kitui County",
                "notify": None, "created_at": CREATED, "metadata": {"excluded": True},
            }])
        assert path == "/rest/v1/data_alerts"
        if state.fail_alerts:
            return httpx.Response(503, json={"message": "private-provider-response"})
        if start == 51 or owner == SECOND:
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[
            {"id": alert_id, "user_id": owner, "alert_type": "new_audit",
             "title": "Baringo report", "body": None, "item_type": "county",
             "item_id": "baringo", "read": alert_id == 1, "created_at": CREATED}
            for alert_id in range(start + 1, min(start + 20, 51) + 1)
        ])

    actual_client = httpx.Client
    monkeypatch.setenv("SUPABASE_URL", "https://account-export.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "inert-test-provider-key")
    monkeypatch.setattr(supabase_auth, "_decode_supabase_jwt", claims)
    monkeypatch.setattr(
        httpx, "Client",
        lambda **kwargs: actual_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    return state


def test_export_uses_live_account_identity_and_only_its_records(client, db_session, provider):
    first = client.get(f"{ENDPOINT}?user_id={SECOND}", headers=authorization(FIRST))
    second = client.get(ENDPOINT, headers=authorization(SECOND))

    assert first.status_code == second.status_code == 200
    assert first.headers["Cache-Control"] == second.headers["Cache-Control"] == "private, no-store"
    data = first.json()
    assert data["profile"] == {
        "id": FIRST, "email": EMAILS[FIRST], "display_name": "Wanjiku",
        "created_at": CREATED, "terms_acceptance": None,
    }
    assert [w["id"] for w in data["watchlist"]] == [1, 2]
    assert all(w["label"] == "Baringo County" and w["notify"] is None for w in data["watchlist"])
    assert [a["id"] for a in data["alerts"]] == list(range(1, 52))
    assert data["newsletter_status"] == "subscribed"
    assert str(SECOND) not in first.text and "metadata" not in first.text
    assert all("user_id" not in row for row in data["watchlist"] + data["alerts"])
    assert second.json()["profile"]["id"] == SECOND
    assert second.json()["newsletter_status"] == "unsubscribed"
    assert second.json()["alerts"] == []
    assert [w["label"] for w in second.json()["watchlist"]] == ["Kitui County"]
    assert db_session.query(User).count() == 0


def test_newsletter_status_requires_verified_current_email(client, provider):
    provider.unverified = True
    response = client.get(ENDPOINT, headers=authorization(FIRST))
    assert response.status_code == 200
    assert response.json()["newsletter_status"] == "unverified_email"


def test_absent_or_invalid_session_reads_no_data(client, provider):
    assert client.get(ENDPOINT).status_code == 401
    assert client.get(ENDPOINT, headers=authorization("invalid")).status_code == 401
    assert provider.requests == []


@pytest.mark.parametrize("condition,status_code", [
    ("wrong_owner", 502), ("fail_alerts", 502), ("missing_user", 401),
])
def test_export_refuses_mismatched_removed_or_incomplete_provider_data(
    client, provider, condition, status_code
):
    setattr(provider, condition, True)
    response = client.get(ENDPOINT, headers=authorization(FIRST))
    assert response.status_code == status_code
    assert response.headers["Cache-Control"] == "private, no-store"
    assert list(response.json()) == ["detail"]
    assert "private-provider-response" not in response.text
    assert "Baringo" not in response.text
