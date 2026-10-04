"""Isolated fixtures; run with --confcutdir=backend/tests/social (never main)."""
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from social.contracts import CapabilitySet, CreatePost
from social.models import SOCIAL_TABLES, Base, SocialAccount
from social.service import SocialService

ACTOR = uuid4()


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def foreign_keys(conn, record):
        conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine, tables=SOCIAL_TABLES)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def account(db, platform="facebook"):
    caps = CapabilitySet(eligible=True, supported_formats=("text", "image", "carousel", "video", "reel"), adapter_available=True, provider_api_version="fixture", feature_states={"publishing": "supported"}, limits={"max_text_length": 5000}, price_class="free")
    row = SocialAccount(id=uuid4(), platform=platform, api_product="fixture", connection_method="fixture", external_account_id=str(uuid4()), display_name="Fixture identity", connection_state="connected", publishing_enabled=True, capability_snapshot=caps.model_dump(mode="json"), granted_scopes=[])
    db.add(row)
    db.commit()
    return row


def draft_body(accounts=(), **fields):
    value = {"title": "Announcement", "content_type": "announcement", "document": {"schema_version": 1, "master": {"text": "Verified announcement", "link": None, "hashtags": [], "media": []}, "targets": [{"account_id": str(a.id), "format": "text", "overrides": {}} for a in accounts]}, "references": []}
    value.update(fields)
    return CreatePost.model_validate(value)


def call(db, body, action, *, route="fixture", key=None, adapters=("facebook", "threads"), actor=ACTOR, status=200):
    svc = SocialService(db, available_adapters=adapters)
    # SQLAlchemy reads autobegin; callers close read-only fixture transactions.
    if db.in_transaction():
        db.rollback()
    return svc.command(actor=actor, route=route, key=key or uuid4(), body=body.model_dump(mode="json", exclude_unset=True), request_id=uuid4(), action=lambda: action(svc), status=status)
