"""借阅与「我的借阅」蓝图（Story 2.1 借阅；「我的借阅」页面在 Story 2.5 补齐）。

路由只做三件事：收集参数 → 调 services → 渲染/映射异常（PC-1）。
未登录拦截（六步判定的 ①）已由 routes/auth.py 的统一守卫完成，能进入
本文件处理函数的请求必然已登录（PC-10：权限判断只在守卫里做一次）。
"""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from config import BizError
from services.loans import borrow_item

bp = Blueprint("loans", __name__)


@bp.post("/borrow")
def borrow():
    raw_item_id = request.form.get("item_id")
    try:
        item_id = int(raw_item_id)
    except (TypeError, ValueError):
        raise BizError(400, "INVALID_INPUT") from None
    due_at = borrow_item(g.current_user["id"], item_id)
    flash(f"借阅成功，应还日期 {due_at[:10]}")
    response = redirect(url_for("items.items_page"))
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/my-loans")
def my_loans_page():
    return render_template("my_loans.html"), 200, {"Cache-Control": "no-store"}
