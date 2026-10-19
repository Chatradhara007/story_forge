"""
Accounts, sign-in and the per-user request budget.

Switched OFF by default (AUTH_REQUIRED=false) so local use works exactly as before: no
sign-in, every book shared. Switch it ON for any deployment people can reach
(render.yaml does): each user then sees only their own books, and each user may add a
limited number of chapters per day (DAILY_CHAPTER_LIMIT), because every chapter costs AI
requests on YOUR NVIDIA key.

Only the Python standard library is used: passwords are hashed with scrypt, and sessions
are signed tokens (HMAC-SHA256) that the website sends as "Authorization: Bearer ...".

What an account can do:
  register, sign in, see itself (/auth/me), change its name, change its password, sign out
  everywhere, reset a forgotten password by email, and delete itself with all its books.

How "sign out everywhere" works without a sessions table: every user has a token_version.
A token carries the version it was made with; bumping the version (sign out everywhere,
password change, password reset) makes every older token invalid at once.
"""
import base64
import hashlib
import hmac
import os
import secrets
import smtplib
import threading
import time
from collections import defaultdict, deque
from email.message import EmailMessage

import psycopg2
from fastapi import HTTPException, Request
import storage

AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
ALLOW_REGISTRATION = os.getenv("ALLOW_REGISTRATION", "true").lower() == "true"
INVITE_CODE = os.getenv("INVITE_CODE", "").strip()           # optional: needed to register
DAILY_CHAPTER_LIMIT = max(0, int(os.getenv("DAILY_CHAPTER_LIMIT", "40")))   # 0 = unlimited
# "Ask" questions and searches also use the AI (one embedding, plus an answer for Ask).
HOURLY_QUESTION_LIMIT = max(0, int(os.getenv("HOURLY_QUESTION_LIMIT", "60")))  # 0 = unlimited
SESSION_DAYS = max(1, int(os.getenv("SESSION_DAYS", "30")))
RESET_MINUTES = 60
# Behind a hosting proxy (Render, Fly, a load balancer) the visitor's real address is the LAST
# entry of X-Forwarded-For (the one the proxy added). Earlier entries are whatever the visitor
# sent, so trusting them would let anyone dodge the password-guessing limit.
BEHIND_PROXY = os.getenv("BEHIND_PROXY", "false").lower() == "true"
# The website address, for links in password-reset emails (e.g. https://storyforge.onrender.com).
APP_URL = os.getenv("APP_URL", "").strip().rstrip("/")

# Email for password resets. Without SMTP_HOST, the reset link is printed in the server log
# (fine for a small team: whoever runs the server passes it on).
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "").strip() or SMTP_USER

_secret = os.getenv("SECRET_KEY", "").strip()
if not _secret:
    if AUTH_REQUIRED:
        print("  [warning] SECRET_KEY is not set: sign-ins will be lost whenever the server restarts.", flush=True)
    _secret = secrets.token_hex(32)
elif AUTH_REQUIRED and len(_secret) < 32:
    print("  [warning] SECRET_KEY is short; use at least 32 random characters.", flush=True)
SECRET = _secret.encode()

# Google sign-in: set GOOGLE_CLIENT_ID (a "Web application" OAuth client from Google Cloud
# console, with this site's address as an authorised JavaScript origin). Empty = no Google button.
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}

COMMON_PASSWORDS = {"password", "password1", "password123", "12345678", "123456789", "1234567890",
                    "qwerty123", "qwertyuiop", "iloveyou", "11111111", "00000000", "abcd1234",
                    "letmein1", "welcome1", "storyforge", "admin123", "passw0rd"}


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


# Checked when the email is unknown, so a wrong email takes as long as a wrong password
# (otherwise the response time tells an attacker which emails have accounts).
_DUMMY_HASH = hash_password(secrets.token_hex(16))


def validate_new_password(password: str, email: str | None = None) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="Use at least 8 characters for the password.")
    if len(password.encode()) > 256:
        raise HTTPException(status_code=422, detail="That password is too long (256 bytes at most).")
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS or len(set(password)) < 4:
        raise HTTPException(status_code=422, detail="That password is too easy to guess. Try a short sentence.")
    if email and lowered == email.strip().lower():
        raise HTTPException(status_code=422, detail="The password can't be your email address.")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_token(user_id: int, version: int = 0) -> str:
    payload = f"{user_id}.{int(time.time()) + SESSION_DAYS * 86400}.{version}"
    signature = hmac.new(SECRET, payload.encode(), hashlib.sha256).digest()
    return f"{_b64(payload.encode())}.{_b64(signature)}"


def read_token(token: str) -> tuple[int, int] | None:
    """(user id, token version) for a valid, unexpired token; None otherwise."""
    try:
        payload_b64, signature_b64 = token.split(".")
        payload = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4)).decode()
        expected = _b64(hmac.new(SECRET, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, signature_b64):
            return None
        parts = payload.split(".")
        user_id, expires = int(parts[0]), int(parts[1])
        version = int(parts[2]) if len(parts) > 2 else 0      # tokens made before versions existed
        return (user_id, version) if expires > time.time() else None
    except (ValueError, UnicodeDecodeError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
_USER_COLUMNS = "id, email, display_name, token_version, created_at"


def _public(user: dict) -> dict:
    return {"id": user["id"], "email": user["email"], "display_name": user["display_name"],
            "created_at": user.get("created_at")}


def get_user(user_id: int) -> dict | None:
    with storage.db() as conn, storage._dict_cursor(conn) as cur:
        cur.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()


def session_for(user: dict) -> dict:
    """What register / login / password changes return: the user and a fresh token."""
    return {"user": _public(user), "token": make_token(user["id"], user.get("token_version") or 0)}


def register(email: str, password: str, display_name: str | None, invite_code: str | None,
             client_ip: str = "?") -> dict:
    if not ALLOW_REGISTRATION:
        raise HTTPException(status_code=403, detail="New accounts are switched off on this StoryForge.")
    if INVITE_CODE and not hmac.compare_digest((invite_code or "").strip().encode(), INVITE_CODE.encode()):
        raise HTTPException(status_code=403, detail="That invite code isn't right.")
    # Every account gets its own daily AI allowance, so creating accounts in bulk is limited.
    _limit("register", client_ip, max_hits=10, window=3600,
           message="Too many new accounts from your network. Try again in an hour.")
    email = email.strip().lower()
    validate_new_password(password, email)
    try:
        with storage.db() as conn, storage._dict_cursor(conn) as cur:
            # One registration at a time, so two "first accounts" can't both adopt the old books.
            cur.execute("SELECT pg_advisory_xact_lock(724001)")
            cur.execute("SELECT 1 FROM users WHERE lower(email) = %s", (email,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="There's already an account with that email. Sign in instead.")
            cur.execute(f"INSERT INTO users (email, password_hash, display_name) VALUES (%s, %s, %s) "
                        f"RETURNING {_USER_COLUMNS}",
                        (email, hash_password(password), (display_name or "").strip() or email.split("@")[0]))
            user = cur.fetchone()
            # The very first account adopts books created before accounts were switched on.
            cur.execute("SELECT COUNT(*) AS n FROM users")
            if cur.fetchone()["n"] == 1:
                cur.execute("UPDATE projects SET owner_id = %s WHERE owner_id IS NULL", (user["id"],))
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="There's already an account with that email. Sign in instead.")
    return user


# ---------------------------------------------------------------------------
# Slowing down guessing and abuse (in memory: one worker process, see the Dockerfile)
# ---------------------------------------------------------------------------
_hits: dict[tuple[str, str], deque] = defaultdict(deque)
_hits_lock = threading.Lock()
_last_sweep = 0.0


def _recent(key: tuple[str, str], window: float) -> deque:
    """The hits for key within the window (older ones dropped). Call with _hits_lock held."""
    global _last_sweep
    now = time.time()
    if now - _last_sweep > 600:          # forget idle keys, so memory doesn't grow forever
        for k in [k for k, q in _hits.items() if not q or q[-1] < now - 3600]:
            del _hits[k]
        _last_sweep = now
    hits = _hits[key]
    while hits and hits[0] < now - window:
        hits.popleft()
    return hits


def _limit(kind: str, who: str, max_hits: int, window: float, message: str, record: bool = True) -> None:
    with _hits_lock:
        hits = _recent((kind, who), window)
        if len(hits) >= max_hits:
            raise HTTPException(status_code=429, detail=message)
        if record:
            hits.append(time.time())


def _count_failure(kind: str, who: str) -> None:
    with _hits_lock:
        _hits[(kind, who)].append(time.time())


def reset_limits() -> None:
    """Forget all counters (used by the tests)."""
    with _hits_lock:
        _hits.clear()


def client_ip(request: Request) -> str:
    if BEHIND_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "")
        last = forwarded.split(",")[-1].strip()
        if last:
            return last
    return request.client.host if request.client else "?"


TOO_MANY_SIGNINS = "Too many failed sign-ins. Wait 15 minutes and try again."


def login(email: str, password: str, ip: str) -> dict:
    email = email.strip().lower()
    # Per address AND per account: the per-account limit can't be dodged by changing address.
    _limit("login-ip", ip, 20, 900, TOO_MANY_SIGNINS, record=False)
    _limit("login-email", email, 10, 900, TOO_MANY_SIGNINS, record=False)
    with storage.db() as conn, storage._dict_cursor(conn) as cur:
        cur.execute(f"SELECT {_USER_COLUMNS}, password_hash FROM users WHERE lower(email) = %s", (email,))
        user = cur.fetchone()
    ok = check_password(password, user["password_hash"] if user else _DUMMY_HASH)
    if user is None or not ok:
        _count_failure("login-ip", ip)
        _count_failure("login-email", email)
        raise HTTPException(status_code=401, detail="Email or password is wrong.")
    with _hits_lock:
        _hits.pop(("login-email", email), None)
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (user["id"],))
    return user


def _google_identity(credential: str) -> dict:
    """Check a Google sign-in credential (an ID token) with Google and return its claims."""
    import json
    import urllib.parse
    import urllib.request
    url = "https://oauth2.googleapis.com/tokeninfo?" + urllib.parse.urlencode({"id_token": credential})
    try:
        with urllib.request.urlopen(url, timeout=10) as reply:
            claims = json.loads(reply.read().decode())
    except Exception:  # noqa: BLE001 - any failure means "not verified"
        raise HTTPException(status_code=401, detail="Google couldn't confirm that sign-in. Try again.")
    if (claims.get("aud") != GOOGLE_CLIENT_ID or claims.get("iss") not in _GOOGLE_ISSUERS
            or str(claims.get("email_verified")).lower() != "true" or not claims.get("email")
            or int(claims.get("exp", 0)) < time.time()):
        raise HTTPException(status_code=401, detail="That Google sign-in isn't valid for this StoryForge.")
    return claims


def google_sign_in(credential: str, invite_code: str | None, ip: str, verify=None) -> dict:
    """
    Sign in with Google. An existing account with the same (Google-verified) email is used;
    otherwise a new account is made, under the same rules as registering (registration open,
    invite code if one is set). Such an account has no password until one is set with
    "Forgot your password?".
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=404, detail="Google sign-in isn't set up on this StoryForge.")
    _limit("login-ip", ip, 20, 900, TOO_MANY_SIGNINS, record=False)
    claims = (verify or _google_identity)(credential)
    email = claims["email"].strip().lower()
    with storage.db() as conn, storage._dict_cursor(conn) as cur:
        cur.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE lower(email) = %s", (email,))
        user = cur.fetchone()
    if user is None:
        if not ALLOW_REGISTRATION:
            raise HTTPException(status_code=403, detail="New accounts are switched off on this StoryForge.")
        if INVITE_CODE and not hmac.compare_digest((invite_code or "").strip().encode(), INVITE_CODE.encode()):
            raise HTTPException(status_code=403, detail="Enter the invite code first, then sign in with Google.")
        _limit("register", ip, max_hits=10, window=3600,
               message="Too many new accounts from your network. Try again in an hour.")
        try:
            with storage.db() as conn, storage._dict_cursor(conn) as cur:
                cur.execute("SELECT pg_advisory_xact_lock(724001)")
                cur.execute(f"INSERT INTO users (email, password_hash, display_name) VALUES (%s, %s, %s) "
                            f"RETURNING {_USER_COLUMNS}",
                            (email, "google$" + secrets.token_hex(16),          # no usable password
                             (claims.get("name") or "").strip()[:80] or email.split("@")[0]))
                user = cur.fetchone()
                cur.execute("SELECT COUNT(*) AS n FROM users")
                if cur.fetchone()["n"] == 1:
                    cur.execute("UPDATE projects SET owner_id = %s WHERE owner_id IS NULL", (user["id"],))
        except psycopg2.errors.UniqueViolation:
            raise HTTPException(status_code=409, detail="That account was just created. Try again.")
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (user["id"],))
    return user


def current_user(request: Request) -> dict | None:
    """FastAPI dependency: the signed-in user, or None when sign-in is switched off."""
    if not AUTH_REQUIRED:
        return None
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    claims = read_token(token) if token else None
    user = get_user(claims[0]) if claims else None
    if user is None or (user["token_version"] or 0) != claims[1]:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return user


def require_user(request: Request) -> dict:
    """Like current_user, but the account pages need a signed-in user even to make sense."""
    if not AUTH_REQUIRED:
        raise HTTPException(status_code=404, detail="Accounts are switched off on this StoryForge.")
    return current_user(request)


def _check_current_password(user_id: int, password: str) -> None:
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
    _limit("password-check", str(user_id), 10, 900, TOO_MANY_SIGNINS, record=False)
    if row is None or not check_password(password, row[0]):
        _count_failure("password-check", str(user_id))
        raise HTTPException(status_code=403, detail="Your current password isn't right.")


def update_profile(user: dict, display_name: str) -> dict:
    with storage.db() as conn, storage._dict_cursor(conn) as cur:
        cur.execute(f"UPDATE users SET display_name = %s WHERE id = %s RETURNING {_USER_COLUMNS}",
                    (display_name.strip() or user["email"].split("@")[0], user["id"]))
        return cur.fetchone()


def _set_password(cur, user_id: int, new_password: str) -> dict:
    """New password; every existing session (token) stops working."""
    cur.execute(f"UPDATE users SET password_hash = %s, token_version = token_version + 1 WHERE id = %s "
                f"RETURNING {_USER_COLUMNS}", (hash_password(new_password), user_id))
    user = cur.fetchone()
    cur.execute("DELETE FROM password_resets WHERE user_id = %s", (user_id,))
    return user


def change_password(user: dict, current: str, new: str) -> dict:
    _check_current_password(user["id"], current)
    validate_new_password(new, user["email"])
    if current == new:
        raise HTTPException(status_code=422, detail="The new password is the same as the current one.")
    with storage.db() as conn, storage._dict_cursor(conn) as cur:
        return _set_password(cur, user["id"], new)


def sign_out_everywhere(user: dict) -> None:
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET token_version = token_version + 1 WHERE id = %s", (user["id"],))


def delete_account(user: dict, password: str) -> None:
    """Delete the account and every book it owns (chapters, facts, warnings: all of it)."""
    _check_current_password(user["id"], password)
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM projects WHERE owner_id = %s", (user["id"],))
        for (project_id,) in cur.fetchall():
            cur.execute("DELETE FROM fact_corrections WHERE project_id = %s", (project_id,))
        cur.execute("DELETE FROM users WHERE id = %s", (user["id"],))   # books go with it (cascade)


# ---------------------------------------------------------------------------
# Forgotten passwords
# ---------------------------------------------------------------------------
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def reset_delivery() -> str:
    return "email" if SMTP_HOST else "server log"


def _send_reset(email: str, link: str) -> None:
    if not SMTP_HOST:
        print(f"  [password reset] link for {email} (valid {RESET_MINUTES} minutes): {link}", flush=True)
        return
    message = EmailMessage()
    message["Subject"] = "Reset your StoryForge password"
    message["From"] = SMTP_FROM
    message["To"] = email
    message.set_content(
        f"Someone (hopefully you) asked to reset the password for {email} on StoryForge.\n\n"
        f"Choose a new password here (the link works once, for {RESET_MINUTES} minutes):\n{link}\n\n"
        "If it wasn't you, ignore this email: your password stays as it is.\n")
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.starttls()
            if SMTP_USER:
                smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        # Never tell the visitor (it would reveal that the account exists); tell the operator.
        print(f"  [password reset] could not email {email}: {error}", flush=True)


def _send_in_background(email: str, link: str) -> None:
    # Sending takes a second or two only when the account exists; doing it in the background
    # keeps the answer time the same either way.
    threading.Thread(target=_send_reset, args=(email, link), daemon=True).start()


def request_reset(email: str, ip: str, base_url: str) -> None:
    """Always 'done', whether or not the account exists (no account fishing)."""
    email = email.strip().lower()
    _limit("reset-ip", ip, 10, 3600, "Too many reset requests. Try again in an hour.")
    _limit("reset-email", email, 3, 3600, "A reset link was already sent. Check your inbox (and spam), "
                                           "or try again in an hour.")
    with storage.db() as conn, storage._dict_cursor(conn) as cur:
        cur.execute("SELECT id FROM users WHERE lower(email) = %s", (email,))
        user = cur.fetchone()
        if user is None:
            return
        token = secrets.token_urlsafe(32)
        cur.execute("DELETE FROM password_resets WHERE user_id = %s OR expires_at < now()", (user["id"],))
        cur.execute("INSERT INTO password_resets (user_id, token_hash, expires_at) "
                    "VALUES (%s, %s, now() + make_interval(mins => %s))",
                    (user["id"], _token_hash(token), RESET_MINUTES))
    _send_in_background(email, f"{APP_URL or base_url.rstrip('/')}/app/#/reset/{token}")


def complete_reset(token: str, new_password: str, ip: str) -> dict:
    _limit("reset-use", ip, 20, 900, "Too many attempts. Try again in 15 minutes.")
    with storage.db() as conn, storage._dict_cursor(conn) as cur:
        cur.execute(
            """SELECT r.user_id, u.email FROM password_resets r JOIN users u ON u.id = r.user_id
               WHERE r.token_hash = %s AND r.used_at IS NULL AND r.expires_at > now() FOR UPDATE""",
            (_token_hash(token),))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=400, detail="This reset link has expired or was already used. "
                                                        "Ask for a new one.")
        validate_new_password(new_password, row["email"])
        return _set_password(cur, row["user_id"], new_password)


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


def refund_chapter(user: dict | None, chapters: int = 1) -> None:
    """Give the allowance back when the work failed (e.g. the AI service was down)."""
    if user is None or not DAILY_CHAPTER_LIMIT:
        return
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE usage_counters SET chapters = GREATEST(chapters - %s, 0) "
                    "WHERE user_id = %s AND day = current_date", (chapters, user["id"]))


def charge_question(user: dict | None) -> None:
    """Ask / search: at most HOURLY_QUESTION_LIMIT per user per hour."""
    if user is None or not HOURLY_QUESTION_LIMIT:
        return
    _limit("question", str(user["id"]), HOURLY_QUESTION_LIMIT, 3600,
           f"You've asked {HOURLY_QUESTION_LIMIT} questions in the last hour. Try again a little later.")
