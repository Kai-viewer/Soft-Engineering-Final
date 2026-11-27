import os
import secrets
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pwdlib import PasswordHash
from sqlalchemy import select

from app.accounts.models import LoginSession, User
from app.core.db import Db
from app.core.web import templates

COOKIE_NAME = "se_session"
SESSION_DURATION = timedelta(hours=8)
password_hasher = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hasher.hash(secrets.token_urlsafe(32))
router = APIRouter(tags=["accounts"])


def token_hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def active_session(request: Request, db: Db) -> LoginSession | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return db.scalar(
        select(LoginSession)
        .join(User)
        .where(
            LoginSession.token_hash == token_hash(token),
            LoginSession.expires_at > datetime.now(timezone.utc),
            User.status == "approved",
        )
    )


ActiveSession = Annotated[LoginSession | None, Depends(active_session)]


def optional_user(request: Request, login: ActiveSession, db: Db) -> User | None:
    user = db.get(User, login.user_id) if login else None
    request.state.user = user
    request.state.csrf_token = login.csrf_token if login else ""
    return user


OptionalUser = Annotated[User | None, Depends(optional_user)]


def current_user(user: OptionalUser) -> User:
    if user is None:
        raise HTTPException(401, "請先登入")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_role(*roles: str):
    def check_role(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(403, "權限不足")
        return user

    return check_role


@router.get("/login", include_in_schema=False)
def login_page(request: Request, user: OptionalUser):
    if user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html")


@router.post("/login", include_in_schema=False)
def login(
    request: Request,
    db: Db,
    previous: ActiveSession,
    email: Annotated[str, Form(max_length=254)],
    password: Annotated[str, Form(max_length=256)],
):
    origin = request.headers.get("origin")
    same_origin = f"{request.url.scheme}://{request.url.netloc}"
    fetch_site = request.headers.get("sec-fetch-site")
    if (origin and origin != same_origin) or fetch_site in {"cross-site", "same-site"}:
        raise HTTPException(403, "請從本站登入")
    account = email.strip().lower()
    if account in {"member", "teacher", "admin"}:
        account = f"{account}@example.test"
    user = db.scalar(select(User).where(User.email == account))
    valid, updated_hash = password_hasher.verify_and_update(
        password, user.password_hash if user else DUMMY_PASSWORD_HASH
    )
    if not valid or user is None or user.status != "approved":
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "帳號或密碼不符，或帳號尚未通過審核。", "email": email},
            status_code=401,
        )
    if previous:
        db.delete(previous)
    if updated_hash:
        user.password_hash = updated_hash
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(
        token_hash=token_hash(token),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(32),
        expires_at=datetime.now(timezone.utc) + SESSION_DURATION,
    ))
    db.commit()
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        max_age=int(SESSION_DURATION.total_seconds()),
    )
    return response


@router.post("/logout", include_in_schema=False)
def logout(login: ActiveSession, db: Db, csrf_token: Annotated[str, Form()] = ""):
    if login is None or not secrets.compare_digest(csrf_token.encode(), login.csrf_token.encode()):
        raise HTTPException(403, "登入已失效或表單驗證失敗")
    db.delete(login)
    db.commit()
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/api/accounts/me")
def profile(user: CurrentUser, login: ActiveSession):
    return {
        "id": user.id, "display_name": user.display_name, "role": user.role,
        "csrf_token": login.csrf_token,
    }
