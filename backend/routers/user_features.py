"""User features router — watchlist, alerts, newsletter.

Endpoints:
  GET/POST/DELETE  /api/v1/user/watchlist     — Manage pinned items
  GET              /api/v1/user/alerts        — Get data alerts
  PATCH            /api/v1/user/alerts/:id    — Mark alert as read
  POST             /api/v1/newsletter/subscribe   — Subscribe (no auth)
  POST             /api/v1/newsletter/unsubscribe — Unsubscribe
  POST             /api/v1/newsletter/send-welcome — Trigger welcome email
  GET              /api/v1/newsletter/unsubscribe-verify — Verify token & unsubscribe
"""

from __future__ import annotations

from typing import List, Optional

from auth import get_current_user
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query, status
from models import DataAlert, NewsletterSubscriber, User, WatchlistItem
from pydantic import ConfigDict, BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

router = APIRouter(tags=["user-features"])


# ── Schemas ─────────────────────────────────────────────────────────


class WatchlistItemCreate(BaseModel):
    item_type: str = Field(..., pattern="^(county|national_category|budget_programme)$")
    item_id: str = Field(..., max_length=100)
    label: str = Field(..., max_length=200)
    notify: bool = True


class WatchlistItemOut(BaseModel):
    id: int
    item_type: str
    item_id: str
    label: str
    notify: bool
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class AlertOut(BaseModel):
    id: int
    alert_type: str
    title: str
    body: Optional[str]
    item_type: Optional[str]
    item_id: Optional[str]
    read: bool
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class NewsletterRequest(BaseModel):
    email: EmailStr


class NewsletterResponse(BaseModel):
    status: str
    message: str


# ── Watchlist ───────────────────────────────────────────────────────


@router.get("/api/v1/user/watchlist", response_model=List[WatchlistItemOut])
def get_watchlist(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all items in the user's watchlist."""
    items = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == current_user.id)
        .order_by(WatchlistItem.created_at.desc())
        .all()
    )
    return [
        WatchlistItemOut(
            id=i.id,
            item_type=i.item_type,
            item_id=i.item_id,
            label=i.label,
            notify=i.notify,
            created_at=i.created_at.isoformat(),
        )
        for i in items
    ]


@router.post("/api/v1/user/watchlist", response_model=WatchlistItemOut, status_code=201)
def add_to_watchlist(
    body: WatchlistItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a county or category to the user's watchlist."""
    existing = (
        db.query(WatchlistItem)
        .filter_by(
            user_id=current_user.id, item_type=body.item_type, item_id=body.item_id
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Item already in watchlist.")

    item = WatchlistItem(
        user_id=current_user.id,
        item_type=body.item_type,
        item_id=body.item_id,
        label=body.label,
        notify=body.notify,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return WatchlistItemOut(
        id=item.id,
        item_type=item.item_type,
        item_id=item.item_id,
        label=item.label,
        notify=item.notify,
        created_at=item.created_at.isoformat(),
    )


@router.delete("/api/v1/user/watchlist/{item_id}", status_code=204)
def remove_from_watchlist(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove an item from the watchlist."""
    item = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.id == item_id, WatchlistItem.user_id == current_user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist item not found.")
    db.delete(item)
    db.commit()


# ── Alerts ──────────────────────────────────────────────────────────


@router.get("/api/v1/user/alerts", response_model=List[AlertOut])
def get_alerts(
    unread_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return alerts for the current user."""
    q = db.query(DataAlert).filter(DataAlert.user_id == current_user.id)
    if unread_only:
        q = q.filter(DataAlert.read == False)  # noqa: E712
    alerts = q.order_by(DataAlert.created_at.desc()).limit(50).all()
    return [
        AlertOut(
            id=a.id,
            alert_type=a.alert_type,
            title=a.title,
            body=a.body,
            item_type=a.item_type,
            item_id=a.item_id,
            read=a.read,
            created_at=a.created_at.isoformat(),
        )
        for a in alerts
    ]


@router.patch("/api/v1/user/alerts/{alert_id}")
def mark_alert_read(
    alert_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark an alert as read."""
    alert = (
        db.query(DataAlert)
        .filter(DataAlert.id == alert_id, DataAlert.user_id == current_user.id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")
    alert.read = True
    db.commit()
    return {"status": "ok"}


@router.post("/api/v1/user/alerts/read-all")
def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark all alerts as read."""
    db.query(DataAlert).filter(
        DataAlert.user_id == current_user.id,
        DataAlert.read == False,  # noqa: E712
    ).update({"read": True})
    db.commit()
    return {"status": "ok"}


# ── Newsletter ──────────────────────────────────────────────────────


@router.post("/api/v1/newsletter/subscribe", response_model=NewsletterResponse)
def subscribe_newsletter(body: NewsletterRequest, db: Session = Depends(get_db)):
    """Subscribe an email to the monthly newsletter (no account required)."""
    existing = db.query(NewsletterSubscriber).filter_by(email=body.email).first()
    if existing:
        if existing.unsubscribed_at:
            existing.unsubscribed_at = None
            db.commit()
            return NewsletterResponse(
                status="resubscribed", message="Welcome back! You're subscribed again."
            )
        return NewsletterResponse(
            status="already_subscribed", message="This email is already subscribed."
        )

    subscriber = NewsletterSubscriber(email=body.email)
    db.add(subscriber)
    db.commit()
    return NewsletterResponse(
        status="subscribed",
        message="You're subscribed! Look out for our monthly digest.",
    )


@router.post("/api/v1/newsletter/unsubscribe", response_model=NewsletterResponse)
def unsubscribe_newsletter(body: NewsletterRequest, db: Session = Depends(get_db)):
    """Unsubscribe from the newsletter."""
    from datetime import datetime, timezone

    existing = db.query(NewsletterSubscriber).filter_by(email=body.email).first()
    if not existing:
        return NewsletterResponse(
            status="not_found", message="Email not found in subscriber list."
        )
    existing.unsubscribed_at = datetime.now(timezone.utc)
    db.commit()
    return NewsletterResponse(
        status="unsubscribed", message="You've been unsubscribed. Sorry to see you go!"
    )


# ── Welcome email & token-verified unsubscribe ─────────────────────


@router.post("/api/v1/newsletter/send-welcome", response_model=NewsletterResponse)
def send_welcome(body: NewsletterRequest):
    """Trigger a welcome email for a new subscriber (best-effort, never blocks)."""
    import threading

    from services.email_service import send_welcome_email

    # Fire-and-forget so the frontend is never blocked by SMTP latency
    threading.Thread(target=send_welcome_email, args=(body.email,), daemon=True).start()

    return NewsletterResponse(status="ok", message="Welcome email queued.")


class UnsubscribeVerifyRequest(BaseModel):
    email: EmailStr
    token: str


@router.post("/api/v1/newsletter/unsubscribe-verify", response_model=NewsletterResponse)
def unsubscribe_verify(body: UnsubscribeVerifyRequest, db: Session = Depends(get_db)):
    """Token-verified unsubscribe — called from the email unsubscribe link."""
    from datetime import datetime, timezone

    from services.email_service import verify_unsubscribe_token

    if not verify_unsubscribe_token(body.email, body.token):
        raise HTTPException(
            status_code=403, detail="Invalid or expired unsubscribe link."
        )

    existing = db.query(NewsletterSubscriber).filter_by(email=body.email).first()
    if not existing:
        return NewsletterResponse(
            status="not_found", message="Email not found in subscriber list."
        )
    if existing.unsubscribed_at:
        return NewsletterResponse(
            status="already_unsubscribed", message="You're already unsubscribed."
        )
    existing.unsubscribed_at = datetime.now(timezone.utc)
    db.commit()
    return NewsletterResponse(
        status="unsubscribed", message="You've been unsubscribed. Sorry to see you go!"
    )
