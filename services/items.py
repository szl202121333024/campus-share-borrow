"""物品 + 在借状态的唯一派生实现（PC-8、AR-5、ADR-007）。

全项目唯一一份「物品联 loans」查询：学生列表、搜索、管理列表（后续故事）
都必须复用本函数，禁止另写第二份 SQL 或引入库存计数列。
items.status 只存 available/unavailable，「在借」由未归还记录派生。
"""

from db import get_db


def _like_escape(text):
    """把 LIKE 通配符转义为普通字符（Story 1.3 的 AC-1.3.3 提前落在唯一实现里）。"""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_items_with_state(query=None, include_unavailable=False):
    """物品 + 在借状态的唯一派生查询（AR-5）；学生端与管理列表共用这一处。

    展示优先级 unavailable > borrowed > available。
    默认过滤 unavailable（学生端不可见）；include_unavailable=True 时列出
    全部物品、含停用项（Story 3.1 AC-3.1.7 管理列表），停用判定不另写第二份 SQL。
    排序：先 book 后 equipment，组内按名称升序。
    """
    sql = (
        "SELECT i.id, i.name, i.category, i.status,"
        "       l.due_at, u.name AS borrower_name,"
        "       CASE"
        "         WHEN i.status = 'unavailable' THEN 'unavailable'"
        "         WHEN l.id IS NOT NULL THEN 'borrowed'"
        "         ELSE 'available'"
        "       END AS display_state"
        "  FROM items i"
        "  LEFT JOIN loans l ON l.item_id = i.id AND l.returned_at IS NULL"
        "  LEFT JOIN users u ON u.id = l.user_id"
    )
    conditions = []
    params = []
    if not include_unavailable:
        conditions.append("i.status != 'unavailable'")
    if query is not None and query.strip():
        conditions.append("i.name LIKE ? ESCAPE '\\'")
        params.append(f"%{_like_escape(query.strip())}%")
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += (" ORDER BY CASE i.category WHEN 'book' THEN 0 ELSE 1 END ASC,"
            " i.name ASC")
    return [dict(row) for row in
            get_db().execute(sql, tuple(params)).fetchall()]
