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


# ⑥ 唯一索引兜底的物理证据特征串：仅这一种 IntegrityError 映射为 409。
# 外键失败等其他完整性错误不得被伪装成业务冲突（ADR-002 §4、AC-2.3.10）。
_UNIQUE_ITEM_CONFLICT = "UNIQUE constraint failed: loans.item_id"


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
        # ⑥：只有部分唯一索引冲突才与 ④ 响应逐字一致（D-016）；
        # 其他完整性错误（外键失败等）原样上抛，由 Flask 呈现 500（AC-2.3.10、ADR-002 §4）。
        if _UNIQUE_ITEM_CONFLICT not in str(exc):
            raise
        raise BizError(409, "ALREADY_BORROWED") from exc
    return due_at


def return_loan(user_id, loan_id):
    """归还一条本人未归还记录（Story 2.2，D-014、PC-6）。

    成败只由条件 UPDATE 的 rowcount 判定：WHERE 同时锁 id、user_id 与
    returned_at IS NULL，并发第二击必然 rowcount == 0，returned_at 只写一次
    （NFR-1.3）。归还路径绝不写物品表——停用物品的 status 属于管理员
    唯一写入口（D-005、AC-2.2.10：services/ 检索物品表写操作命中 0）。
    """
    conn = get_db()
    with write_transaction():
        cur = conn.execute(
            "UPDATE loans SET returned_at = ?"
            " WHERE id = ? AND user_id = ? AND returned_at IS NULL",
            (now_text(), loan_id, user_id),
        )
        if cur.rowcount == 1:
            return
        # rowcount == 0：一次额外 SELECT 区分「本人已归还」与「不存在/非本人」
        row = conn.execute(
            "SELECT returned_at FROM loans WHERE id = ? AND user_id = ?",
            (loan_id, user_id),
        ).fetchone()
        if row is not None and row["returned_at"] is not None:
            raise BizError(409, "ALREADY_RETURNED")
        # 他人记录与不存在 id 在此合并为同一响应（D-011、AC-2.2.6）
        raise BizError(404, "RESOURCE_NOT_FOUND")


def list_user_loans(user_id):
    """「我的借阅」最小可用版的唯一查询（Story 2.2；完整版在 Story 2.5）。

    逾期标记在此一条 SQL 内派生：returned_at IS NULL 且 due_at 早于当前时间
    才为逾期；归还后 returned_at 非空，is_overdue 自动归 0（AC-2.2.4），
    模板只做渲染、不做换算。
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT l.id AS loan_id, i.name, l.borrowed_at, l.due_at, l.returned_at,"
        "       CASE WHEN l.returned_at IS NULL AND l.due_at < ?"
        "            THEN 1 ELSE 0 END AS is_overdue"
        "  FROM loans l"
        "  JOIN items i ON i.id = l.item_id"
        " WHERE l.user_id = ?"
        " ORDER BY l.id DESC",
        (now_text(), user_id),
    ).fetchall()
    return [dict(row) for row in rows]
