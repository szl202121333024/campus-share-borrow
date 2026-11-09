"""物品浏览蓝图（Story 1.1 提供最小可访问列表页；搜索行为在 Story 1.3 补齐断言）。

路由只做三件事：收集参数 → 调 services → 渲染/映射异常（PC-1）。
"""

from flask import Blueprint, render_template, request

from services.items import list_items_with_state

bp = Blueprint("items", __name__)


@bp.get("/items")
def items_page():
    keyword = request.args.get("q")
    item_list = list_items_with_state(query=keyword)
    response = render_template("items.html", item_list=item_list)
    return response, 200, {"Cache-Control": "no-store"}
