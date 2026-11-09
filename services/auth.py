"""学号认证、会话加载与安全跳转（Story 1.2）。

密码只经 security.verify_password 校验；不存在的学号使用固定假哈希，
确保每次登录尝试恰好执行一次密码哈希校验。
"""

from datetime import datetime, timezone
from urllib.parse import urlsplit

from flask import current_app, g, request, session
from itsdangerous import BadPayload, BadSignature

from config import BizError
from db import get_db, now_text
from security import verify_password

DUMMY_PASSWORD_HASH = (
    "pbkdf2:sha256:1000000$YD8T8CnKumc5Afto$"
    "74d34d7550a939abb6dba4152a350a7cc76b4cdf9a9db4c35f1fe70fb7612bef"
)
SESSION_EXPIRED_MESSAGE = "登录已过期"


def authenticate_user(student_id, password):
    """校验白名单用户字段；所有认证失败共用同一个真实 401 错误。"""
    user = get_db().execute(
        "SELECT id, student_id, name, password_hash, role"
        " FROM users WHERE student_id = ?",
        (student_id,),
    ).fetchone()
    password_hash = user["password_hash"] if user is not None else DUMMY_PASSWORD_HASH
    password_valid = verify_password(password_hash, password)
    if user is None or not password_valid:
        raise BizError(401, "INVALID_CREDENTIALS")
    return user


def begin_user_session(user):
    """认证会话只写用户标识、角色和登录时间。"""
    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    session["login_at"] = now_text()


def clear_user_session(response):
    """清空会话并用与原 cookie 相同的属性显式删除浏览器 cookie。"""
    session.clear()
    # 删除由本函数显式完成，避免 Flask 在响应保存阶段重复写删除头。
    session.modified = False
    interface = current_app.session_interface
    response.delete_cookie(
        interface.get_cookie_name(current_app),
        path=interface.get_cookie_path(current_app),
        domain=interface.get_cookie_domain(current_app),
        secure=interface.get_cookie_secure(current_app),
        httponly=interface.get_cookie_httponly(current_app),
        samesite=interface.get_cookie_samesite(current_app),
    )
    g.current_user = None


def safe_next_path(value):
    """只接受本站绝对路径；外部、协议相对及非路径输入统一回退列表页。"""
    fallback = "/items"
    if not value or value != value.strip() or "\\" in value:
        return fallback
    if any(ord(character) < 32 for character in value):
        return fallback
    try:
        parsed = urlsplit(value)
    except ValueError:
        return fallback
    if parsed.scheme or parsed.netloc:
        return fallback
    if not value.startswith("/") or value.startswith("//"):
        return fallback
    if not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return fallback
    return value


def _signed_cookie_is_expired():
    """验证签名但忽略年龄后读取签名时间，以精确区分过期与无效签名。"""
    interface = current_app.session_interface
    raw_cookie = request.cookies.get(interface.get_cookie_name(current_app))
    if not raw_cookie:
        return False
    serializer = interface.get_signing_serializer(current_app)
    if serializer is None:
        return False
    try:
        _data, signed_at = serializer.loads(
            raw_cookie,
            max_age=None,
            return_timestamp=True,
        )
    except (BadSignature, BadPayload):
        return False
    if signed_at.tzinfo is None:
        signed_at = signed_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > (
        signed_at + current_app.permanent_session_lifetime
    )


def load_current_user():
    """每请求加载当前用户；签名时间超过闲置期限时单独标记过期。"""
    if "current_user" in g:
        return g.current_user

    g.current_user = None
    g.session_expired = _signed_cookie_is_expired()
    if g.session_expired:
        if session:
            session.clear()
        return None

    if not all(key in session for key in ("user_id", "role", "login_at")):
        return None

    user = get_db().execute(
        "SELECT id, student_id, name, role FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()
    if user is None or user["role"] != session["role"]:
        session.clear()
        return None

    g.current_user = user
    return user
