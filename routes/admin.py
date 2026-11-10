"""管理蓝图（Story 3.1，FR-6 新增 + 管理列表）。

权限边界（D-012、PC-10）——蓝图级统一拦截，全库唯一的 role 授权判定点：
- bp = Blueprint(..., url_prefix="/admin")：守卫与路由同前缀，物理上不会漏挂；
- @bp.before_request：进入本蓝图的任何请求（含未来 3.2~3.4 的删除/停用/恢复）
  先过这里——未登录 302 → /login?next=（AC-3.1.1），非管理员 403 FORBIDDEN
  （AC-3.1.2）。业务代码（路由体与 services/）内不得再出现任何 role 判断；
- routes/auth.py 的全站守卫只保留 /admin 前缀的「未登录 302」（认证拦截），
  不含任何 role 分支——授权语义只在本文件成立一处。

路由只做三件事：收集参数 → 调 services → 渲染/映射异常（PC-1）。
本故事只提供新增与列表：编辑物品不在 v1（改名会破坏借阅历史的名称一致性，
v1 已按 D-007 砍掉快照字段——人类裁决「只增不删改」）；删除/停用/恢复属 Story 3.2~3.4。
"""

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from config import BizError
from services.admin import CATEGORIES, create_item
from services.auth import load_current_user
from services.items import list_items_with_state

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
def guard_admin_blueprint():
    """蓝图级唯一授权拦截点（D-012）：先保登录 302，再拦非管理员 403。"""
    user = load_current_user()  # 幂等：全站守卫已加载时直接命中 g 缓存
    if user is None:
        return redirect(url_for("auth.login", next=request.path))
    if user["role"] != "admin":
        raise BizError(403, "FORBIDDEN")
    return None


@bp.route("/items", methods=("GET", "POST"))
def admin_items():
    """管理列表（含停用项与在借人）与新增表单；POST 成功走 PRG 302（PC-9、ADR-001）。"""
    if request.method == "POST":
        create_item(request.form.get("name"), request.form.get("category"))
        flash("已添加")
        return redirect(url_for("admin.admin_items"))
    item_list = list_items_with_state(include_unavailable=True)
    return (
        render_template("admin_items.html", item_list=item_list, categories=CATEGORIES),
        200,
        {"Cache-Control": "no-store"},
    )
