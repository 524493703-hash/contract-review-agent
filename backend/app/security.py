from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import User


bearer = HTTPBearer(auto_error=False)
_user_cache: dict[str, tuple[float, dict]] = {}
_user_cache_lock = Lock()


def _user_snapshot(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "password_hash": "",
        "name": user.name,
        "email": user.email,
        "department": user.department,
        "role": user.role,
        "is_active": user.is_active,
    }


def cache_authenticated_user(user: User) -> None:
    expires_at = monotonic() + max(1, get_settings().auth_cache_seconds)
    with _user_cache_lock:
        _user_cache[user.id] = (expires_at, _user_snapshot(user))


def _cached_user(user_id: str) -> User | None:
    now = monotonic()
    with _user_cache_lock:
        cached = _user_cache.get(user_id)
        if not cached:
            return None
        expires_at, snapshot = cached
        if expires_at <= now:
            _user_cache.pop(user_id, None)
            return None
    return User(**snapshot)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "username": user.username,
        "role": user.role,
        "name": user.name,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    settings = get_settings()
    if settings.sso_enabled:
        username = request.headers.get("x-authenticated-user") or request.headers.get("oai-authenticated-user-email")
        if username:
            user = db.scalar(select(User).where(User.username == username))
            if user:
                return user
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
        user_id = payload.get("sub")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效") from exc
    user = _cached_user(user_id) if user_id else None
    if not user and user_id:
        user = db.get(User, user_id)
        if user:
            cache_authenticated_user(user)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不可用")
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles and user.role != "系统管理员":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权执行此操作")
        return user

    return dependency
