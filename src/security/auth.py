"""Authentication helpers for Slice 1.

Password hashing uses Argon2id (argon2-cffi). Session tokens are opaque random
strings; only their SHA-256 hash is persisted.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()

SESSION_IDLE_MINUTES = int(os.getenv("ASRBRAIN_SESSION_IDLE_MINUTES", "60"))
SESSION_ABSOLUTE_HOURS = int(os.getenv("ASRBRAIN_SESSION_ABSOLUTE_HOURS", "24"))


def hash_password(password: str) -> str:
    if not password or len(password) < 12:
        raise ValueError("password must be at least 12 characters")
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _ph.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    idle = now + timedelta(minutes=SESSION_IDLE_MINUTES)
    absolute = now + timedelta(hours=SESSION_ABSOLUTE_HOURS)
    expiry = min(idle, absolute)
    return now.isoformat(), expiry.isoformat()


def create_user(conn: sqlite3.Connection, email: str, password: str,
                display_name: str = "", status: str = "active") -> str:
    import uuid
    user_id = "user-" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO users(user_id, email, display_name, password_hash, status, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (user_id, email.strip().lower(), display_name or email.split("@")[0],
         hash_password(password), status, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    return user_id


def authenticate(conn: sqlite3.Connection, email: str, password: str) -> Optional[str]:
    row = conn.execute(
        "SELECT user_id, password_hash, status FROM users WHERE email = ?",
        (email.strip().lower(),)).fetchone()
    if not row:
        return None
    user_id, password_hash, status = row
    if status != "active":
        return None
    if not verify_password(password, password_hash):
        return None
    conn.execute("UPDATE users SET last_login_at = ? WHERE user_id = ?",
                 (datetime.now(timezone.utc).isoformat(), user_id))
    conn.commit()
    return user_id


def create_session(conn: sqlite3.Connection, user_id: str, user_agent: str = "",
                   ip: str = "") -> str:
    token = new_session_token()
    now, expiry = session_expiry()
    conn.execute(
        "INSERT INTO user_sessions(session_id, user_id, token_hash, created_at, "
        "expires_at, last_seen_at, user_agent, ip) VALUES (?,?,?,?,?,?,?,?)",
        ("sess-" + secrets.token_hex(8), user_id, hash_session_token(token),
         now, expiry, now, user_agent, ip))
    conn.commit()
    return token


def resolve_session(conn: sqlite3.Connection, token: str) -> Optional[str]:
    if not token:
        return None
    token_hash = hash_session_token(token)
    row = conn.execute(
        "SELECT user_id, expires_at, revoked_at FROM user_sessions WHERE token_hash = ?",
        (token_hash,)).fetchone()
    if not row:
        return None
    user_id, expires_at, revoked_at = row
    if revoked_at:
        return None
    try:
        expiry = datetime.fromisoformat(expires_at)
    except Exception:
        return None
    if expiry < datetime.now(timezone.utc):
        return None
    conn.execute("UPDATE user_sessions SET last_seen_at = ? WHERE token_hash = ?",
                 (datetime.now(timezone.utc).isoformat(), token_hash))
    conn.commit()
    return user_id


def revoke_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("UPDATE user_sessions SET revoked_at = ? WHERE token_hash = ?",
                 (datetime.now(timezone.utc).isoformat(), hash_session_token(token)))
    conn.commit()


def revoke_all_sessions(conn: sqlite3.Connection, user_id: str) -> None:
    conn.execute("UPDATE user_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                 (datetime.now(timezone.utc).isoformat(), user_id))
    conn.commit()
