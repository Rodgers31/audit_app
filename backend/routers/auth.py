"""DEPRECATED — Auth is handled by Supabase (frontend direct). This file is kept for reference only.

Authentication & user management router.

Endpoints:
  POST /api/v1/auth/register   — Create account
  POST /api/v1/auth/login      — Get JWT tokens
  POST /api/v1/auth/refresh    — Refresh access token
  GET  /api/v1/auth/me         — Current user profile
  PATCH /api/v1/auth/me        — Update profile
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    authenticate_user,
    create_access_token,
    get_current_user,
    get_password_hash,
    get_user_by_email,
)
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, status
from models import User
from pydantic import ConfigDict, BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ── Request / Response schemas ──────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    display_name: Optional[str] = Field(None, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = ACCESS_TOKEN_EXPIRE_MINUTES * 60
    user: "UserPublic"


class UserPublic(BaseModel):
    id: int
    email: str
    display_name: Optional[str]
    roles: list
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=120)


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """Create a new free account."""
    existing = get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=body.email,
        password_hash=get_password_hash(body.password),
        display_name=body.display_name,
        roles=["citizen"],
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return TokenResponse(
        access_token=token,
        user=UserPublic(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            roles=user.roles or [],
            created_at=user.created_at.isoformat(),
        ),
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate and return JWT."""
    user = authenticate_user(db, body.email, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return TokenResponse(
        access_token=token,
        user=UserPublic(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            roles=user.roles or [],
            created_at=user.created_at.isoformat(),
        ),
    )


@router.get("/me", response_model=UserPublic)
async def me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return UserPublic(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        roles=current_user.roles or [],
        created_at=current_user.created_at.isoformat(),
    )


@router.patch("/me", response_model=UserPublic)
async def update_profile(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update display name or other profile fields."""
    if body.display_name is not None:
        current_user.display_name = body.display_name
    db.commit()
    db.refresh(current_user)
    return UserPublic(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        roles=current_user.roles or [],
        created_at=current_user.created_at.isoformat(),
    )
