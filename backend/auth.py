"""
Accounts, sign-in and the per-user request budget.

Switched OFF by default (AUTH_REQUIRED=false) so local use works exactly as before: no
sign-in, every book shared. Switch it ON for any deployment people can reach
(render.yaml does): each user then sees only their own books, and each user may add a
limited number of chapters per day (DAILY_CHAPTER_LIMIT), because every chapter costs AI
requests on YOUR NVIDIA key.

Only the Python standard library is used: passwords are hashed with scrypt, and sessions
are signed tokens (HMAC-SHA256) that the website sends as "Authorization: Bearer ...".
"""
import base64
import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request
import storage

AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
ALLOW_REGISTRATION = os.getenv("ALLOW_REGISTRATION", "true").lower() == "true"
INVITE_CODE = os.getenv("INVITE_CODE", "").strip()           # optional: needed to register
DAILY_CHAPTER_LIMIT = max(0, int(os.getenv("DAILY_CHAPTER_LIMIT", "40")))   # 0 = unlimited
SESSION_DAYS = 30

_secret = os.getenv("SECRET_KEY", "").strip()
if not _secret:
    if AUTH_REQUIRED:
        print("  [warning] SECRET_KEY is not set: sign-ins will be lost whenever the server restarts.", flush=True)
    _secret = secrets.token_hex(32)
SECRET = _secret.encode()


# ---------------------------------------------------------------------------
# Passwords and session tokens
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(candidate.hex(), digest)
    except (ValueError, TypeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_token(user_id: int) -> str:
    payload = f"{user_id}.{int(time.time()) + SESSION_DAYS * 86400}"
    signature = hmac.new(SECRET, payload.encode(), hashlib.sha256).digest()
    return f"{_b64(payload.encode())}.{_b64(signature)}"


def read_token(token: str) -> int | None:
    try:
        payload_b64, signature_b64 = token.split(".")
        payload = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4)).decode()
        expected = _b64(hmac.new(SECRET, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, signature_b64):
            return None
        user_id, expires = payload.split(".")
        return int(user_id) if int(expires) > time.time() else None
    except (ValueError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def _public(user: dict) -> dict:
    return {"id": user["id"], "email": user["email"], "display_name": user["display_name"]}


def get_user(user_id: int) -> dict | None:
    with storage.db() as conn, storage._dict_cursor(conn) as cur:
        cur.execute("SELECT id, email, display_name FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()


def register(email: str, password: str, display_name: str | None, invite_code: str | None) -> dict:
    if not ALLOW_REGISTRATION:
        raise HTTPException(status_code=403, detail="New accounts are switched off on this StoryForge.")
    if INVITE_CODE and not hmac.compare_digest((invite_code or "").strip(), INVITE_CODE):
        raise HTTPException(status_code=403, detail="That invite code isn't right.")
    email = email.strip().lower()
    with storage.db() as conn, storage._dict_cursor(conn) as cur:
        cur.execute("SELECT 1 FROM users WHERE lower(email) = %s", (email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="There's already an account with that email. Sign in instead.")
        cur.execute("INSERT INTO users (email, password_hash, display_name) VALUES (%s, %s, %s) "
                    "RETURNING id, email, display_name",
                    (email, hash_password(password), (display_name or "").strip() or email.split("@")[0]))
        user = cur.fetchone()
        # The very first account adopts books created before accounts were switched on.
        cur.execute("SELECT COUNT(*) AS n FROM users")
        if cur.fetchone()["n"] == 1:
            cur.execute("UPDATE projects SET owner_id = %s WHERE owner_id IS NULL", (user["id"],))
    return _public(user)


# Slow down password guessing: at most 10 failed sign-ins per address per 15 minutes.
_failures: dict[str, deque] = defaultdict(deque)
_failures_lock = threading.Lock()


def login(email: str, password: str, client_ip: str) -> dict:
    with _failures_lock:
        recent = _failures[client_ip]
        while recent and recent[0] < time.time() - 900:
            recent.popleft()
        if len(recent) >= 10:
            raise HTTPException(status_code=429, detail="Too many failed sign-ins. Wait 15 minutes and try again.")
    with storage.db() as conn, storage._dict_cursor(conn) as cur:
        cur.execute("SELECT id, email, display_name, password_hash FROM users WHERE lower(email) = %s",
                    (email.strip().lower(),))
        user = cur.fetchone()
    if user is None or not check_password(password, user["password_hash"]):
        with _failures_lock:
            _failures[client_ip].append(time.time())
        raise HTTPException(status_code=401, detail="Email or password is wrong.")
    return _public(user)


def current_user(request: Request) -> dict | None:
    """FastAPI dependency: the signed-in user, or None when sign-in is switched off."""
    if not AUTH_REQUIRED:
        return None
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    user_id = read_token(token) if token else None
    user = get_user(user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return user


# ---------------------------------------------------------------------------
# Request budget
# ---------------------------------------------------------------------------
def usage_today(user_id: int) -> int:
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute("SELECT chapters FROM usage_counters WHERE user_id = %s AND day = current_date", (user_id,))
        row = cur.fetchone()
        return row[0] if row else 0


def charge_chapter(user: dict | None, chapters: int = 1) -> None:
    """Count chapter work against the user's daily budget; refuse once it's used up."""
    if user is None or not DAILY_CHAPTER_LIMIT:
        return
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO usage_counters (user_id, day, chapters) VALUES (%s, current_date, %s)
               ON CONFLICT (user_id, day) DO UPDATE SET chapters = usage_counters.chapters + EXCLUDED.chapters
               RETURNING chapters""",
            (user["id"], chapters))
        used = cur.fetchone()[0]
        if used > DAILY_CHAPTER_LIMIT:
            conn.rollback()
            raise HTTPException(
                status_code=429,
                detail=f"You've used today's allowance of {DAILY_CHAPTER_LIMIT} chapter checks. "
                       f"It resets at midnight (server time).")
