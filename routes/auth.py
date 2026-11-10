"""登录、登出与全站唯一访问守卫（Story 1.2）。"""

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from config import BizError
from services.auth import (
    SESSION_EXPIRED_MESSAGE,
    authenticate_user,
    begin_user_session,
    clear_user_session,
    load_current_user,
    safe_next_path,
)

bp = Blueprint("auth", __name__)


@bp.before_app_request
def guard_protected_paths():
    """在路由解析及 404/405 之前执行全站统一【认证】拦截。

    只管「有没有登录」（302 → /login?next=），不含任何 role 分支——
    /admin/* 的管理员授权（403 FORBIDDEN）由 routes/admin.py 的蓝图级
    before_request 统一拦截（D-012：全库唯一 role 判定点）。
    此处保留 /admin 前缀的原因：未登录访问任意 /admin/... （含未注册路径）
    也先 302 到登录页，保持 Story 1.2 AC-1.2.5 的「认证先于路由解析」语义。
    """
    # Normalize path: strip trailing slash so /my-loans/ → /my-loans, etc.
    path = request.path.rstrip("/") or "/"
    current_user = load_current_user()
    is_protected_path = (
        path == "/my-loans"
        or path == "/borrow"
        or path == "/return"
        or path.startswith("/borrow/")
        or path.startswith("/return/")
        or path == "/admin"
        or path.startswith("/admin/")
    )
    if not is_protected_path:
        return None
    if current_user is None:
        if g.get("session_expired"):
            flash(SESSION_EXPIRED_MESSAGE)
        return redirect(url_for("auth.login", next=path))
    return None


@bp.app_context_processor
def inject_current_user():
    return {"current_user": g.get("current_user")}


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "GET":
        if g.get("current_user") is not None:
            return redirect(url_for("items.items_page"))
        next_path = safe_next_path(request.args.get("next"))
        return (
            render_template("login.html", next_path=next_path, student_id=""),
            200,
            {"Cache-Control": "no-store"},
        )

    student_id = request.form.get("student_id", "").strip()
    password = request.form.get("password", "")
    next_path = safe_next_path(request.form.get("next"))
    try:
        user = authenticate_user(student_id, password)
    except BizError as err:
        # Only clear the session if it was not already authenticated AND has content;
        # a valid user who accidentally submits bad credentials on POST /login
        # should NOT be silently logged out.
        if g.current_user is None and session:
            session.clear()
        g.current_user = None
        return (
            render_template(
                "login.html",
                next_path=next_path,
                student_id=student_id,
                error_code=err.error_code,
                message=err.message,
            ),
            err.status_code,
            {"Cache-Control": "no-store"},
        )

    begin_user_session(user)
    return redirect(next_path)


@bp.post("/logout")
def logout():
    response = redirect(url_for("items.items_page"))
    clear_user_session(response)
    return response
