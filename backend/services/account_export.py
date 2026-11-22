"""The portable view of an authenticated account's personal data."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import NewsletterSubscriber
from supabase_admin import get_account_records


class ProfileExport(BaseModel):
    id: str
    email: str | None
    display_name: str | None
    created_at: datetime
    terms_acceptance: None = None


class WatchlistExport(BaseModel):
    id: int
    item_type: str
    item_id: str
    label: str
    notify: bool | None
    created_at: datetime | None


class AlertExport(BaseModel):
    id: int
    alert_type: str
    title: str
    body: str | None
    item_type: str | None
    item_id: str | None
    read: bool | None
    created_at: datetime | None


class AccountExport(BaseModel):
    profile: ProfileExport
    watchlist: list[WatchlistExport]
    alerts: list[AlertExport]
    newsletter_status: Literal[
        "subscribed", "unsubscribed", "not_subscribed", "unverified_email"
    ]


class AccountAuthRecord(BaseModel):
    email: str | None = None
    email_confirmed_at: datetime | None = None
    created_at: datetime


def export_account(user_id: str, db: Session) -> AccountExport:
    auth_record, profile, watchlist, alerts = get_account_records(user_id)
    user = AccountAuthRecord.model_validate(auth_record)
    newsletter_status = "unverified_email"
    if user.email and user.email_confirmed_at:
        # Newsletter records live in the data DB and are keyed on the current email.
        # The verified auth record is the only authority for this lookup.
        subscriptions = (
            db.query(NewsletterSubscriber.unsubscribed_at)
            .filter(func.lower(NewsletterSubscriber.email) == user.email.lower())
            .all()
        )
        if not subscriptions:
            newsletter_status = "not_subscribed"
        elif any(row.unsubscribed_at is None for row in subscriptions):
            newsletter_status = "subscribed"
        else:
            newsletter_status = "unsubscribed"

    return AccountExport(
        profile=ProfileExport(
            id=user_id,
            email=user.email,
            display_name=profile.get("display_name") if profile else None,
            created_at=user.created_at,
        ),
        watchlist=[WatchlistExport.model_validate(row) for row in watchlist],
        alerts=[AlertExport.model_validate(row) for row in alerts],
        newsletter_status=newsletter_status,
    )
