"""Accounts: sign-up, sign-in, sessions, password change / reset, account deletion, limits."""
import pytest
import auth


@pytest.fixture
def accounts(client, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_REQUIRED", True)
    monkeypatch.setattr(auth, "ALLOW_REGISTRATION", True)
    monkeypatch.setattr(auth, "INVITE_CODE", "")
    sent = []
    monkeypatch.setattr(auth, "_send_in_background", lambda email, link: sent.append((email, link)))
    client.sent = sent
    return client


def register(client, email="ines@gull.io", password="lamp-keeper-1", **extra):
    return client.post("/auth/register", json={"email": email, "password": password, **extra})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_sign_in_and_me(accounts):
    r = register(accounts, display_name="Ines")
    assert r.status_code == 201
    token = r.json()["token"]
    me = accounts.get("/auth/me", headers=bearer(token)).json()
    assert me["user"]["email"] == "ines@gull.io" and me["user"]["display_name"] == "Ines"
    assert "password_hash" not in me["user"]
    r = accounts.post("/auth/login", json={"email": " INES@gull.io ", "password": "lamp-keeper-1"})
    assert r.status_code == 200 and r.json()["token"]
    assert register(accounts).status_code == 409                       # same email again


def test_weak_passwords_are_refused(accounts):
    assert register(accounts, password="short").status_code == 422
    assert register(accounts, password="password123").status_code == 422
    assert register(accounts, password="aaaaaaaaaaaa").status_code == 422
    assert register(accounts, email="me@x.io", password="me@x.io").status_code == 422


def test_invite_code_and_closed_registration(accounts, monkeypatch):
    monkeypatch.setattr(auth, "INVITE_CODE", "gullstone")
    assert register(accounts).status_code == 403
    assert register(accounts, invite_code="gullstone").status_code == 201
    monkeypatch.setattr(auth, "ALLOW_REGISTRATION", False)
    assert register(accounts, email="other@x.io", invite_code="gullstone").status_code == 403


def test_wrong_password_and_lockout_per_account(accounts):
    register(accounts)
    for _ in range(10):
        assert accounts.post("/auth/login", json={"email": "ines@gull.io", "password": "nope-nope"}).status_code == 401
    # Locked, even with the right password, until the window passes.
    assert accounts.post("/auth/login", json={"email": "ines@gull.io", "password": "lamp-keeper-1"}).status_code == 429
    # Unknown emails get the same answer as wrong passwords.
    r = accounts.post("/auth/login", json={"email": "nobody@gull.io", "password": "whatever-1"})
    assert r.status_code == 401 and r.json()["detail"] == "Email or password is wrong."


def test_tampered_and_expired_tokens_are_refused(accounts, monkeypatch):
    token = register(accounts).json()["token"]
    payload, signature = token.split(".")
    assert accounts.get("/projects", headers=bearer(payload + ".x" + signature[1:])).status_code == 401
    monkeypatch.setattr(auth, "SESSION_DAYS", -1)
    expired = auth.make_token(1, 0)
    assert accounts.get("/projects", headers=bearer(expired)).status_code == 401


def test_sign_out_everywhere_ends_every_session(accounts):
    first = register(accounts).json()["token"]
    second = accounts.post("/auth/login", json={"email": "ines@gull.io", "password": "lamp-keeper-1"}).json()["token"]
    assert accounts.post("/auth/logout-everywhere", headers=bearer(first)).status_code == 200
    assert accounts.get("/projects", headers=bearer(first)).status_code == 401
    assert accounts.get("/projects", headers=bearer(second)).status_code == 401


def test_change_password(accounts):
    old = register(accounts).json()["token"]
    wrong = accounts.post("/auth/password", headers=bearer(old),
                          json={"current_password": "not-it-at-all", "new_password": "brass-key-22"})
    assert wrong.status_code == 403
    r = accounts.post("/auth/password", headers=bearer(old),
                      json={"current_password": "lamp-keeper-1", "new_password": "brass-key-22"})
    assert r.status_code == 200
    new = r.json()["token"]
    assert accounts.get("/projects", headers=bearer(old)).status_code == 401    # other sessions end
    assert accounts.get("/projects", headers=bearer(new)).status_code == 200
    assert accounts.post("/auth/login", json={"email": "ines@gull.io", "password": "lamp-keeper-1"}).status_code == 401
    assert accounts.post("/auth/login", json={"email": "ines@gull.io", "password": "brass-key-22"}).status_code == 200


def test_update_display_name(accounts):
    token = register(accounts).json()["token"]
    r = accounts.patch("/auth/me", headers=bearer(token), json={"display_name": "  Keeper Ines "})
    assert r.status_code == 200 and r.json()["user"]["display_name"] == "Keeper Ines"


def test_forgotten_password_reset_flow(accounts):
    register(accounts)
    old_session = accounts.post("/auth/login", json={"email": "ines@gull.io", "password": "lamp-keeper-1"}).json()["token"]
    # Unknown email: same answer, nothing sent.
    assert accounts.post("/auth/forgot", json={"email": "nobody@gull.io"}).status_code == 202
    assert accounts.sent == []
    assert accounts.post("/auth/forgot", json={"email": "Ines@gull.io"}).status_code == 202
    (email, link), = accounts.sent
    assert email == "ines@gull.io" and "/app/#/reset/" in link
    token = link.rsplit("/", 1)[1]
    assert accounts.post("/auth/reset", json={"token": token, "new_password": "short"}).status_code == 422
    r = accounts.post("/auth/reset", json={"token": token, "new_password": "fog-horn-1987"})
    assert r.status_code == 200 and r.json()["token"]
    # The link works once; old sessions end; the new password works.
    assert accounts.post("/auth/reset", json={"token": token, "new_password": "fog-horn-1988"}).status_code == 400
    assert accounts.get("/projects", headers=bearer(old_session)).status_code == 401
    assert accounts.post("/auth/login", json={"email": "ines@gull.io", "password": "fog-horn-1987"}).status_code == 200
    assert accounts.post("/auth/reset", json={"token": "x" * 43, "new_password": "fog-horn-1989"}).status_code == 400


def test_reset_links_expire(accounts):
    import storage
    register(accounts)
    accounts.post("/auth/forgot", json={"email": "ines@gull.io"})
    token = accounts.sent[0][1].rsplit("/", 1)[1]
    with storage.db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE password_resets SET expires_at = now() - interval '1 minute'")
    assert accounts.post("/auth/reset", json={"token": token, "new_password": "fog-horn-1987"}).status_code == 400


def test_delete_account_removes_its_books(accounts):
    a = register(accounts).json()["token"]
    b = register(accounts, email="pip@gull.io", password="lens-polish-3").json()["token"]
    book = accounts.post("/projects", json={"name": "The Gullstone Light"}, headers=bearer(a)).json()
    accounts.post("/projects", json={"name": "Pip's notebook"}, headers=bearer(b))
    assert accounts.post("/auth/delete-account", headers=bearer(a), json={"password": "wrong-one"}).status_code == 403
    assert accounts.post("/auth/delete-account", headers=bearer(a), json={"password": "lamp-keeper-1"}).status_code == 200
    assert accounts.get("/projects", headers=bearer(a)).status_code == 401
    assert accounts.post("/auth/login", json={"email": "ines@gull.io", "password": "lamp-keeper-1"}).status_code == 401
    import storage
    assert storage.get_project(book["id"]) is None
    assert [p["name"] for p in accounts.get("/projects", headers=bearer(b)).json()["projects"]] == ["Pip's notebook"]


def test_first_account_adopts_existing_books(accounts, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_REQUIRED", False)
    accounts.post("/projects", json={"name": "Before accounts"})
    monkeypatch.setattr(auth, "AUTH_REQUIRED", True)
    first = register(accounts).json()["token"]
    second = register(accounts, email="pip@gull.io", password="lens-polish-3").json()["token"]
    assert [p["name"] for p in accounts.get("/projects", headers=bearer(first)).json()["projects"]] == ["Before accounts"]
    assert accounts.get("/projects", headers=bearer(second)).json()["projects"] == []


def test_account_endpoints_need_sign_in_and_accounts_on(accounts, monkeypatch):
    assert accounts.post("/auth/logout-everywhere").status_code == 401
    assert accounts.patch("/auth/me", json={"display_name": "x"}).status_code == 401
    monkeypatch.setattr(auth, "AUTH_REQUIRED", False)
    assert accounts.patch("/auth/me", json={"display_name": "x"}).status_code == 404
    assert accounts.get("/auth/me").json() == {"user": None, "auth_required": False}


def test_failed_ai_work_is_not_counted_against_the_allowance(accounts, fake_ai, monkeypatch):
    monkeypatch.setattr(auth, "DAILY_CHAPTER_LIMIT", 1)
    token = register(accounts).json()["token"]
    book = accounts.post("/projects", json={"name": "B"}, headers=bearer(token)).json()
    fake_ai.fail_next = 100                                       # the AI service is down
    r = accounts.post(f"/projects/{book['id']}/chapters", json={"chapter_id": "c1", "text": "x"}, headers=bearer(token))
    assert r.status_code == 502
    fake_ai.fail_next = 0
    r = accounts.post(f"/projects/{book['id']}/chapters", json={"chapter_id": "c1", "text": "x"}, headers=bearer(token))
    assert r.status_code == 200


def test_questions_are_budgeted(accounts, fake_ai, monkeypatch):
    monkeypatch.setattr(auth, "HOURLY_QUESTION_LIMIT", 2)
    token = register(accounts).json()["token"]
    book = accounts.post("/projects", json={"name": "B"}, headers=bearer(token)).json()
    accounts.post(f"/projects/{book['id']}/chapters", json={"chapter_id": "c1", "text": "x"}, headers=bearer(token))
    codes = [accounts.get(f"/projects/{book['id']}/search?q=lamp", headers=bearer(token)).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_security_headers(accounts):
    r = accounts.get("/app/")
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    assert accounts.get("/auth/config").headers["cache-control"] == "no-store"


def test_busy_book_refuses_quick_changes(accounts, monkeypatch):
    import jobs
    monkeypatch.setattr(auth, "AUTH_REQUIRED", False)
    book = accounts.post("/projects", json={"name": "B"}).json()
    lock = jobs.book_lock(book["id"])
    import threading
    held = threading.Event(); release = threading.Event()
    def hold():
        with lock:
            held.set(); release.wait(5)
    t = threading.Thread(target=hold); t.start(); held.wait()
    try:
        monkeypatch.setattr(jobs.book_free, "__defaults__", (0.1,))
        assert accounts.delete(f"/projects/{book['id']}").status_code == 409
    finally:
        release.set(); t.join()
    assert accounts.delete(f"/projects/{book['id']}").status_code == 200


def test_google_sign_in_creates_then_reuses_the_account(accounts, monkeypatch):
    monkeypatch.setattr(auth, "GOOGLE_CLIENT_ID", "client-123.apps.googleusercontent.com")
    claims = {"email": "Mara@Gull.io", "name": "Mara Calloway"}
    monkeypatch.setattr(auth, "_google_identity", lambda credential: claims)
    r = accounts.post("/auth/google", json={"credential": "x" * 40})
    assert r.status_code == 200 and r.json()["user"]["email"] == "mara@gull.io"
    assert r.json()["user"]["display_name"] == "Mara Calloway"
    again = accounts.post("/auth/google", json={"credential": "y" * 40})
    assert again.json()["user"]["id"] == r.json()["user"]["id"]
    # A Google-only account has no usable password.
    assert accounts.post("/auth/login", json={"email": "mara@gull.io", "password": "google"}).status_code == 401
    assert "accounts.google.com" in accounts.get("/").headers.get("content-security-policy", "")


def test_google_sign_in_is_off_without_a_client_id(accounts, monkeypatch):
    monkeypatch.setattr(auth, "GOOGLE_CLIENT_ID", "")
    assert accounts.post("/auth/google", json={"credential": "x" * 40}).status_code == 404
    assert accounts.get("/auth/config").json()["google_client_id"] is None
