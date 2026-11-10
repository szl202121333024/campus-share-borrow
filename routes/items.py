"""物品浏览蓝图（Story 1.1 最小列表；Story 1.3 搜索；Story 2.5 登录态限额指示）。

路由只做三件事：收集参数 → 调 services → 渲染/映射异常（PC-1）。
"""

from flask import Blueprint, g, render_template, request

from services.items import list_items_with_state
from services.loans import get_remaining_quota

bp = Blueprint("items", __name__)


@bp.get("/items")
def items_page():
    keyword = request.args.get("q")
    item_list = list_items_with_state(query=keyword)
    # AC-2.5.3/AC-2.5.8：限额指示直接调用单点函数 get_remaining_quota()，
    # 每次渲染恰好一次；匿名不调用（AC-2.5.5）。路由手不写任何 COUNT。
    user = getattr(g, "current_user", None)
    remaining = get_remaining_quota(user["id"]) if user else None
    response = render_template(
        "items.html", item_list=item_list, remaining_quota=remaining
    )
    return response, 200, {"Cache-Control": "no-store"}
