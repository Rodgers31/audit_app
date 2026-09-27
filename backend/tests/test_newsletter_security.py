"""Exercise real signatures and isolated database writes; never contact SMTP."""
import importlib
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from models import NewsletterSubscriber
from services import email_service


@pytest.fixture(autouse=True)
def no_mail(monkeypatch):
    send = Mock(return_value=True)
    monkeypatch.setattr(email_service, "send_welcome_email", send)
    monkeypatch.setattr(email_service, "_hmac_key", lambda: b"newsletter-test-key")
    return send


def test_arbitrary_address_cannot_trigger_welcome(client, no_mail):
    response = client.post(
        "/api/v1/newsletter/send-welcome", json={"email": "victim@example.com"}
    )
    assert response.status_code in (404, 405)
    no_mail.assert_not_called()


def test_anonymous_address_cannot_unsubscribe(client, db_session):
    row = NewsletterSubscriber(email="owner@example.com")
    db_session.add(row)
    db_session.commit()
    response = client.post("/api/v1/newsletter/unsubscribe", json={"email": row.email})
    assert response.status_code in (404, 405)
    db_session.refresh(row)
    assert row.unsubscribed_at is None


def test_new_subscription_mails_once_and_retries_do_not(client, db_session, no_mail):
    for email in ("New@Example.com", "new@example.com", "NEW@example.com"):
        assert (
            client.post(
                "/api/v1/newsletter/subscribe", json={"email": email}
            ).status_code
            == 200
        )
    assert db_session.query(NewsletterSubscriber).count() == 1
    no_mail.assert_called_once_with("new@example.com")


def test_anonymous_resubscription_cannot_undo_opt_out(client, db_session, no_mail):
    row = NewsletterSubscriber(
        email="owner@example.com", unsubscribed_at=datetime.now(timezone.utc)
    )
    db_session.add(row)
    db_session.commit()
    response = client.post("/api/v1/newsletter/subscribe", json={"email": row.email})
    assert response.status_code == 403
    db_session.refresh(row)
    assert row.unsubscribed_at is not None
    no_mail.assert_not_called()


def test_signature_ownership_tampering_and_idempotent_replay(
    client, db_session, no_mail
):
    email = "owner@example.com"
    db_session.add(NewsletterSubscriber(email=email))
    db_session.commit()
    token = email_service.generate_unsubscribe_token(email)
    # No timestamp check exists here: only the real signature can refuse these.
    for bad in (
        "0" * 64,
        token[:-1] + ("0" if token[-1] != "0" else "1"),
        email_service.generate_unsubscribe_token("other@example.com"),
        "☃",
    ):
        response = client.post(
            "/api/v1/newsletter/unsubscribe-verify", json={"email": email, "token": bad}
        )
        assert response.status_code == 403
        assert db_session.query(NewsletterSubscriber).one().unsubscribed_at is None
    for expected in ("unsubscribed", "already_unsubscribed"):
        response = client.post(
            "/api/v1/newsletter/unsubscribe-verify",
            json={"email": email, "token": token},
        )
        assert response.json()["status"] == expected
    # Address possession also authorizes resubscription, without another email.
    response = client.post(
        "/api/v1/newsletter/subscribe", json={"email": email, "token": token}
    )
    assert response.json()["status"] == "resubscribed"
    assert db_session.query(NewsletterSubscriber).one().unsubscribed_at is None
    no_mail.assert_not_called()


def test_signing_key_is_stable_for_local_settings(monkeypatch):
    module = importlib.import_module("config.settings")
    monkeypatch.setattr(module, "get_secret", lambda *a: None)
    one = module.Settings(ENVIRONMENT="development", _env_file=None)
    two = module.Settings(ENVIRONMENT="development", _env_file=None)
    assert one.SECRET_KEY == one.SECRET_KEY == two.SECRET_KEY


def test_missing_production_key_fails_closed(monkeypatch):
    module = importlib.import_module("config.settings")
    monkeypatch.setattr(module, "get_secret", lambda *a: None)
    config = module.Settings(ENVIRONMENT="production", _env_file=None)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _ = config.SECRET_KEY


def test_configured_key_survives_new_settings_instances(monkeypatch):
    module = importlib.import_module("config.settings")
    monkeypatch.setattr(module, "get_secret", lambda *a: "configured-stable-key")
    for _ in range(2):
        assert module.Settings(_env_file=None).SECRET_KEY == "configured-stable-key"


def test_missing_production_key_returns_503_without_writes(
    client, db_session, monkeypatch, no_mail
):
    module = importlib.import_module("config.settings")
    monkeypatch.setattr(module, "get_secret", lambda *a: None)
    config = module.Settings(ENVIRONMENT="production", _env_file=None)
    monkeypatch.setattr(email_service, "_hmac_key", lambda: config.SECRET_KEY.encode())
    for path, body in [
        ("subscribe", {"email": "new@example.com"}),
        ("unsubscribe-verify", {"email": "new@example.com", "token": "0" * 64}),
    ]:
        assert client.post("/api/v1/newsletter/" + path, json=body).status_code == 503
    assert db_session.query(NewsletterSubscriber).count() == 0
    no_mail.assert_not_called()


def test_signature_check_is_actually_exercised(monkeypatch):
    original = email_service.hmac.compare_digest
    compare = Mock(wraps=original)
    monkeypatch.setattr(email_service.hmac, "compare_digest", compare)
    assert (
        email_service.verify_unsubscribe_token("owner@example.com", "0" * 64) is False
    )
    assert compare.call_count == 1
    token = email_service.generate_unsubscribe_token("owner@example.com")
    assert email_service.verify_unsubscribe_token("owner@example.com", token) is True
    assert compare.call_count == 2


def test_concurrent_signup_retries_create_one_welcome(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi import BackgroundTasks
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Query, Session
    from routers.user_features import NewsletterRequest, subscribe_newsletter

    engine = create_engine("sqlite:///" + str(tmp_path / "race.sqlite"))
    NewsletterSubscriber.__table__.create(engine)
    barrier = Barrier(2)

    class RacingQuery(Query):
        def first(self):
            result = super().first()
            if not self.session.info.get("read"):
                self.session.info["read"] = True
                barrier.wait(timeout=10)
            return result

    def signup(email):
        with Session(engine, query_cls=RacingQuery) as db:
            tasks = BackgroundTasks()
            result = subscribe_newsletter(NewsletterRequest(email=email), tasks, db)
            return result.status, len(tasks.tasks)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(signup, ["Owner@Example.com", "owner@example.com"]))
        assert sorted(results) == [("already_subscribed", 0), ("subscribed", 1)]
        with Session(engine) as db:
            assert db.query(NewsletterSubscriber).count() == 1
    finally:
        engine.dispose()


def test_configured_signature_survives_process_restart():
    import os
    import subprocess
    import sys

    env = {
        **os.environ,
        "SECRET_BACKEND": "env",
        "ENVIRONMENT": "production",
        "SECRET_KEY": "test-only-stable-signing-key",
    }
    snippet = 'from services.email_service import generate_unsubscribe_token; print(generate_unsubscribe_token("owner@example.com"))'
    from pathlib import Path

    outputs = [
        subprocess.check_output(
            [sys.executable, "-c", snippet],
            env=env,
            text=True,
            cwd=Path(__file__).resolve().parents[1],
        ).strip()
        for _ in range(2)
    ]
    assert outputs[0] == outputs[1] and len(outputs[0]) == 64
