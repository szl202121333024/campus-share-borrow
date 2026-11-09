"""借阅业务（Story 2.1，PC-5、PC-9）。

六步判定顺序（D-006、D-008、D-016，序号最小者优先）：
①未登录 → 302（由 routes/auth.py 的统一守卫完成，本函数不会被调用）
②物品不存在 → 404 RESOURCE_NOT_FOUND ┐ 同一条 SELECT（D-008）
③物品已停用   → 409 ITEM_UNAVAILABLE  ┘
④物品已被借出（含本人已持有）→ 409 ALREADY_BORROWED ┐ 同一条聚合查询
⑤本人额度已满 → 409 LIMIT_EXCEEDED ┘（逾期计入额度，FR-5）
⑥唯一索引兜底（并发竞态）→ 捕获 IntegrityError，响应与 ④ 逐字一致

整个写路径包在 write_transaction()（BEGIN IMMEDIATE）内（AR-1、D-009）：
②③④⑤ 的读取与 ⑥ 的 INSERT 处于同一事务，失败整体回滚（NFR-1.5）。
"""

import sqlite3

from config import BORROW_LIMIT, BizError
from db import due_text, get_db, now_text, write_transaction


def _loan_counts(conn, item_id, user_id):
    """④⑤ 共用的唯一一条聚合查询：一次算出本人额度占用与该物品的未归还记录数。

    逾期记录 returned_at IS NULL，天然计入 user_active（AC-2.1.12）。
    """
    row = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN l.user_id = ? THEN 1 ELSE 0 END), 0) AS user_active,"
        "       COALESCE(SUM(CASE WHEN l.item_id = ? THEN 1 ELSE 0 END), 0) AS item_active"
        "  FROM loans l"
        " WHERE l.returned_at IS NULL"
        "   AND (l.user_id = ? OR l.item_id = ?)",
        (user_id, item_id, user_id, item_id),
    ).fetchone()
    return dict(row)


def borrow_item(user_id, item_id):
    """借阅一件物品，成功返回 due_at 文本；失败抛 BizError（真实 4xx + 错误码）。"""
    conn = get_db()
    try:
        with write_transaction():
            # ②③：存在性与停用状态读同一行（D-008），全服务仅此一条对 items 的 SELECT
            item = conn.execute(
                "SELECT id, status FROM items WHERE id = ?", (item_id,)
            ).fetchone()
            if item is None:
                raise BizError(404, "RESOURCE_NOT_FOUND")
            if item["status"] == "unavailable":
                raise BizError(409, "ITEM_UNAVAILABLE")

            # ④⑤：一条聚合查询同时判定（D-008、D-013）
            counts = _loan_counts(conn, item_id, user_id)
            if counts["item_active"] > 0:
                raise BizError(409, "ALREADY_BORROWED")
            if counts["user_active"] >= BORROW_LIMIT:
                raise BizError(409, "LIMIT_EXCEEDED")

            # 正常路径下 ⑥ 几乎不可达（ADR-002 §4），仅并发竞态时触发；
            # 捕获后抛出与 ④ 完全相同的 BizError，两个分支的响应逐字一致（D-016）。
            borrowed_at = now_text()
            due_at = due_text(borrowed_at)
            conn.execute(
                "INSERT INTO loans (item_id, user_id, borrowed_at, due_at)"
                " VALUES (?, ?, ?, ?)",
                (item_id, user_id, borrowed_at, due_at),
            )
    except sqlite3.IntegrityError as exc:
        raise BizError(409, "ALREADY_BORROWED") from exc
    return due_at
