"""借阅业务（Story 2.1，PC-5、PC-9）。

六步判定顺序（D-006、D-008、D-016，序号最小者优先）：
①未登录 → 302（由 routes/auth.py 的统一守卫完成，本函数不会被调用）
②物品不存在 → 404 RESOURCE_NOT_FOUND ┐ 同一条 SELECT（D-008）
③物品已停用   → 409 ITEM_UNAVAILABLE  ┘
④物品已被借出（含本人已持有）→ 409 ALREADY_BORROWED ┐ 同一 BEGIN IMMEDIATE
⑤本人额度已满 → 409 LIMIT_EXCEEDED ┘（逾期计入额度，FR-5）  写事务内判定（D-025）
⑥唯一索引兜底（并发竞态）→ 捕获 IntegrityError，响应与 ④ 逐字一致

整个写路径包在 write_transaction()（BEGIN IMMEDIATE）内（AR-1、D-009）：
②③④⑤ 的读取与 ⑥ 的 INSERT 处于同一事务，失败整体回滚（NFR-1.5）。

Story 2.4 起额度单点化（D-013、AC-2.4.7）：④ 改为非聚合单行存在性查询，
⑤ 调用全项目唯一额度聚合 get_remaining_quota()；两条读取仍同处一个
BEGIN IMMEDIATE 写事务，快照一致性由事务串行化保证，D-008 意图不变
（订正记录见 decision-log D-025，test_loans 的 2.1 断言随之同步）。
"""

import sqlite3
from datetime import datetime

from config import BORROW_LIMIT, TIME_FORMAT, BizError
from db import due_text, get_db, now_text, write_transaction


def _active_loan_for_item(conn, item_id):
    """④ 存在性判定：该物品是否已有未归还记录（含本人持有）。

    刻意写成非聚合单行查询（无 COUNT(*)）：额度计数 SQL 全项目只允许
    存在于 get_remaining_quota() 一处，④ 若用聚合就会造出第二份计数（AC-2.4.7）。
    """
    return conn.execute(
        "SELECT user_id FROM loans"
        " WHERE item_id = ? AND returned_at IS NULL LIMIT 1",
        (item_id,),
    ).fetchone()


def get_remaining_quota(student_id):
    """额度唯一真相（PC-7、D-013、AC-2.4.7）：函数体内只有这一条 COUNT(*) 聚合。

    返回「剩余可借数」，借满时返回 0；前置校验（本函数被 borrow_item ⑤
    调用）与页面限额指示（Story 2.5）共用这一处，逾期记录 returned_at IS NULL
    天然计入（AC-2.1.12）。
    """
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) AS active_count FROM loans"
        " WHERE user_id = ? AND returned_at IS NULL",
        (student_id,),
    ).fetchone()
    return BORROW_LIMIT - row["active_count"]


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

            # ④：存在性判定（非聚合，避免与额度计数重复）
            if _active_loan_for_item(conn, item_id) is not None:
                raise BizError(409, "ALREADY_BORROWED")
            # ⑤：额度调用全库唯一真相 get_remaining_quota()（同一连接、同一事务）
            if get_remaining_quota(user_id) <= 0:
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
    """我的借阅完整版的唯一查询（Story 2.5，AC-2.5.1~2.5.2）。

    只返回未归还记录：returned_at IS NOT NULL 一律过滤（AC-2.5.1）。
    已归还记录的即时反馈由各归还请求的 flash 承担，归还后记录从本页
    消失，自然不再标红（兼容 AC-2.2.4 的验收文本）。
    逾期按用户口径在 Python 层计算：is_overdue 与 overdue_days =
    当前日期 − 应还日期的日期差；due_at 当天不算逾期（AC-2.5.2）。
    模板只渲染布尔与天数，不做任何时间换算。
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT l.id AS loan_id, i.name, l.borrowed_at, l.due_at"
        "  FROM loans l"
        "  JOIN items i ON i.id = l.item_id"
        " WHERE l.user_id = ? AND l.returned_at IS NULL"
        " ORDER BY l.due_at ASC, l.id DESC",
        (user_id,),
    ).fetchall()
    today = datetime.now().date()
    result = []
    for row in rows:
        loan = dict(row)
        due_date = datetime.strptime(loan["due_at"], TIME_FORMAT).date()
        overdue_days = (today - due_date).days
        loan["is_overdue"] = overdue_days > 0
        loan["overdue_days"] = overdue_days if overdue_days > 0 else 0
        result.append(loan)
    return result
