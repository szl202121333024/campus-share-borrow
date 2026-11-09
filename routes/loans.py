"""最小“我的借阅”页面；借阅查询与借还业务属于后续故事。"""

from flask import Blueprint, render_template

bp = Blueprint("loans", __name__)


@bp.get("/my-loans")
def my_loans_page():
    return render_template("my_loans.html"), 200, {"Cache-Control": "no-store"}
