"""Story 1.2：学号登录、登出、会话与统一访问控制（AC-1.2.1 ~ 1.2.10）。"""

import logging
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlparse

import pytest
from itsdangerous.timed import TimestampSigner

import db as db_module
import services.auth as auth_service
from config import ERROR_MESSAGES, TIME_FORMAT


def _login(client, student_id="2024001", password="stu123456", next_path=None):
    data = {"student_id": student_id, "password": password}
    if next_path is not None:
        data["next"] = next_path
    return client.post("/login", data=data)


def _set_signed_session(client, app, monkeypatch, signed_at):
    """用指定签名时间生成真实会话 cookie，不使用 sleep 制造过期。"""
    serializer = app.session_interface.get_signing_serializer(app)
    payload = {
        "user_id": 1,
        "role": "student",
        "login_at": signed_at.strftime(TIME_FORMAT),
    }
    with monkeypatch.context() as patch:
        patch.setattr(
            TimestampSigner,
            "get_timestamp",
            lambda _self: int(signed_at.timestamp()),
        )
        cookie_value = serializer.dumps(payload)
    client.set_cookie("session", cookie_value, path="/")
    return cookie_value


def test_ac_1_2_1_valid_seed_login_creates_session_and_opens_my_loans(client):
    response = _login(client)

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/items"
    assert "session=" in response.headers["Set-Cookie"]
    with client.session_transaction() as current_session:
        assert set(current_session) == {"user_id", "role", "login_at"}
        assert current_session["user_id"] == 1
        assert current_session["role"] == "student"
    assert client.get("/my-loans").status_code == 200


@pytest.mark.parametrize(
    ("student_id", "password"),
    [
        ("no-such-student", "wrong-password"),
        ("2024001", "wrong-password"),
        ("", "stu123456"),
        ("2024001", ""),
    ],
)
def test_ac_1_2_2_all_login_failures_are_identical_and_create_no_session(
    client, student_id, password
):
    response = _login(client, student_id=student_id, password=password)

    assert response.status_code == 401
    html = response.get_data(as_text=True)
    assert "INVALID_CREDENTIALS" in html
    assert ERROR_MESSAGES["INVALID_CREDENTIALS"] in html
    assert "session=" not in response.headers.get("Set-Cookie", "")
    assert "wrong-password" not in html


def test_ac_1_2_3_authenticated_get_login_redirects_without_form(client):
    _login(client)

    response = client.get("/login")

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/items"
    assert '<input id="password"' not in response.get_data(as_text=True)


def test_ac_1_2_4_post_logout_deletes_cookie_and_protects_page(client):
    _login(client)

    response = client.post("/logout")

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/items"
    cookie_header = response.headers["Set-Cookie"]
    assert "session=;" in cookie_header
    assert "Expires=" in cookie_header
    protected = client.get("/my-loans")
    assert protected.status_code == 302
    assert parse_qs(urlparse(protected.headers["Location"]).query)["next"] == [
        "/my-loans"
    ]
    assert client.get("/logout").status_code == 405


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/my-loans"),
        ("POST", "/borrow"),
        ("POST", "/return/1"),
        ("GET", "/admin/items"),
        ("POST", "/admin/items"),
    ],
)
def test_ac_1_2_5_guard_precedes_routing_and_preserves_original_path(
    client, method, path
):
    response = client.open(path, method=method)

    assert response.status_code == 302
    location = urlparse(response.headers["Location"])
    assert location.path == "/login"
    assert parse_qs(location.query)["next"] == [path]


def test_ac_1_2_6_guest_list_and_search_remain_public(client):
    assert client.get("/items").status_code == 200
    assert client.get("/items?q=算法").status_code == 200


def test_ac_1_2_7_student_admin_path_is_forbidden_not_redirected(client):
    _login(client)

    response = client.get("/admin/items")

    assert response.status_code == 403
    assert "FORBIDDEN" in response.get_data(as_text=True)
    assert "Location" not in response.headers


def test_ac_1_2_8_expired_and_active_signed_sessions_are_distinguished(
    client, app, monkeypatch
):
    expired_at = datetime.now(timezone.utc) - timedelta(hours=24, seconds=2)
    _set_signed_session(client, app, monkeypatch, expired_at)

    expired = client.get("/my-loans", follow_redirects=True)

    assert expired.history[0].status_code == 302
    assert "登录已过期" in expired.get_data(as_text=True)

    client.delete_cookie("session", path="/")
    active_at = datetime.now(timezone.utc) - timedelta(hours=1)
    _set_signed_session(client, app, monkeypatch, active_at)
    assert client.get("/my-loans").status_code == 200


def test_ac_1_2_9_password_hashes_and_secrets_never_leak(
    client, app, caplog, capsys
):
    with app.app_context():
        hashes = [
            row["password_hash"]
            for row in db_module.get_db().execute("SELECT password_hash FROM users")
        ]
    assert hashes
    assert all(value.startswith("pbkdf2:sha256:") for value in hashes)

    caplog.set_level(logging.DEBUG)
    success = _login(client)
    failed = _login(client, password="sensitive-wrong-password")
    list_page = client.get("/items")
    cookie_value = client.get_cookie("session")
    captured = capsys.readouterr()
    observable_text = "".join(
        [
            success.get_data(as_text=True),
            failed.get_data(as_text=True),
            list_page.get_data(as_text=True),
            caplog.text,
            captured.out,
            captured.err,
        ]
    )
    for secret in ["stu123456", "admin123456", "sensitive-wrong-password", *hashes]:
        assert secret not in observable_text
    if cookie_value is not None:
        assert cookie_value.value not in caplog.text
        assert cookie_value.value not in captured.out
        assert cookie_value.value not in captured.err


def test_ac_1_2_10_unknown_student_uses_one_fixed_dummy_hash_check(
    client, monkeypatch
):
    calls = []
    real_verify = auth_service.verify_password

    def counting_verify(password_hash, plain_password):
        calls.append((password_hash, plain_password))
        return real_verify(password_hash, plain_password)

    monkeypatch.setattr(auth_service, "verify_password", counting_verify)
    unknown = _login(client, student_id="missing", password="bad-password")

    assert len(calls) == 1
    assert calls[0][0] == auth_service.DUMMY_PASSWORD_HASH

    calls.clear()
    wrong_password = _login(client, student_id="2024001", password="bad-password")
    assert len(calls) == 1
    assert calls[0][0] != auth_service.DUMMY_PASSWORD_HASH
    assert wrong_password.status_code == unknown.status_code == 401
    for response in (unknown, wrong_password):
        html = response.get_data(as_text=True)
        assert "INVALID_CREDENTIALS" in html
        assert ERROR_MESSAGES["INVALID_CREDENTIALS"] in html


def test_safe_next_redirect_and_failed_form_preservation(client):
    safe_path = "/my-loans"
    failed = _login(client, password="bad-password", next_path=safe_path)
    assert failed.status_code == 401
    assert f'name="next" value="{safe_path}"' in failed.get_data(as_text=True)

    success = _login(client, next_path=safe_path)
    assert success.status_code == 302
    assert urlparse(success.headers["Location"]).path == safe_path


@pytest.mark.parametrize(
    "next_path",
    [
        "https://evil.example/steal",
        "//evil.example/steal",
        "//[::1",
        "javascript:alert(1)",
        "items",
        "/\\evil.example/steal",
    ],
)
def test_unsafe_next_falls_back_to_items(client, next_path):
    response = _login(client, next_path=next_path)

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/items"


def test_permanent_cookie_attributes_and_refresh_each_request(client, app):
    response = _login(client)

    cookie = SimpleCookie()
    cookie.load(response.headers["Set-Cookie"])
    session_cookie = cookie["session"]
    assert session_cookie["httponly"]
    assert session_cookie["samesite"] == "Lax"
    assert not session_cookie["secure"]
    assert session_cookie["path"] == "/"
    assert session_cookie["expires"]
    assert app.permanent_session_lifetime == timedelta(hours=24)
    assert app.config["SESSION_REFRESH_EACH_REQUEST"] is True

    refreshed = client.get("/my-loans")
    assert refreshed.status_code == 200
    assert "session=" in refreshed.headers["Set-Cookie"]


def test_invalid_signature_is_anonymous_without_expired_message(
    client, app, monkeypatch
):
    cookie_value = _set_signed_session(
        client,
        app,
        monkeypatch,
        datetime.now(timezone.utc),
    )
    client.set_cookie("session", cookie_value + "tampered", path="/")

    response = client.get("/my-loans", follow_redirects=True)

    assert response.history[0].status_code == 302
    assert "登录已过期" not in response.get_data(as_text=True)


def test_non_admin_navigation_hides_admin_entry_and_login_failure_has_no_password(
    client,
):
    guest_html = client.get("/items").get_data(as_text=True)
    assert "后台管理" not in guest_html

    _login(client)
    student_html = client.get("/items").get_data(as_text=True)
    assert "退出登录" in student_html
    assert "后台管理" not in student_html


def test_cache_control_no_store_on_protected_pages(client):
    """Guard against cached auth-sensitive responses."""
    resp = client.get("/login")
    assert resp.headers.get("Cache-Control") == "no-store"

    _login(client)
    my_loans = client.get("/my-loans")
    assert my_loans.status_code == 200
    assert my_loans.headers.get("Cache-Control") == "no-store"


def test_admin_login_success(client):
    """Admin login creates a session; /admin/items route is Story 3.1."""
    response = _login(
        client, student_id="A001", password="admin123456"
    )
    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/items"

    with client.session_transaction() as current_session:
        assert current_session["role"] == "admin"
        assert current_session["user_id"] == 3


def test_tampered_role_session_is_rejected(client, app, monkeypatch):
    """Role tampering: set role='admin' in cookie for a student user → treated as anonymous."""
    from itsdangerous.timed import TimestampSigner
    from datetime import timedelta, timezone

    serializer = app.session_interface.get_signing_serializer(app)
    payload = {
        "user_id": 1,  # student user (id=1, role='student' in DB)
        "role": "admin",  # tampered: claims admin but DB has student
        "login_at": (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).strftime(TIME_FORMAT),
    }
    signed_at = datetime.now(timezone.utc) - timedelta(hours=1)
    with monkeypatch.context() as patch:
        patch.setattr(
            TimestampSigner,
            "get_timestamp",
            lambda _self: int(signed_at.timestamp()),
        )
        cookie_value = serializer.dumps(payload)

    client.set_cookie("session", cookie_value, path="/")
    response = client.get("/my-loans", follow_redirects=True)
    # role mismatch → load_current_user clears session → treated as anonymous → 302 to login
    assert response.history[0].status_code == 302
    assert parse_qs(urlparse(response.history[0].headers["Location"]).query)["next"] == ["/my-loans"]
