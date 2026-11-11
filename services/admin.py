"""管理员业务（Story 3.1 新增 + Story 3.2 删除，FR-6，PC-1、PC-9）。

Story 3.1 校验口径（FR-6）：
- 名称去首尾空白后必须为 1–50 字符（长度真相 = config.MAX_NAME_LEN）；
- 类别必须是 book 或 equipment（严格字面值，不做大小写宽松）；
- 名称允许重复——一物一行（ADR-006），不做唯一校验。
任一校验失败统一抛 400 INVALID_INPUT（PC-9：真实 4xx，禁止 200+错误文案）。

写入 status 恒为 'available' 字面量（AR-4：'borrowed' 永不入库，CHECK 兜底）。

Story 3.2 删除口径（D-010、D-020）：在借 409 拦截；无在借时同事务显式
清理已归还记录后删物品；拒绝 ON DELETE CASCADE，外键兜底竞态（见 delete_item）。

v1 无编辑功能（人类裁决：改名会使借阅历史失去名称快照——D-007 已砍快照字段）；
停用/恢复属 Story 3.3~3.4。
权限拦截不在本文件：403 由 routes/admin.py 的蓝图级守卫统一完成（D-012、D-026），
业务代码内不得出现任何 role 判断。
"""

import sqlite3

from config import MAX_NAME_LEN, BizError
from db import get_db, now_text, write_transaction

CATEGORIES = ("book", "equipment")

# 外键兜底的物理证据特征串（Story 3.2）：loans.item_id 外键不带
# ON DELETE CASCADE（D-020），业务拦截被绕过时由数据库拒绝删行——
# 仅此一种 IntegrityError 映射 409，其余原样上抛（ADR-008 同口径）。
_FK_LOANS_ITEM = "FOREIGN KEY constraint failed"


def create_item(raw_name, category):
    """新增一件物品，返回新行 id；校验失败抛 BizError(400, INVALID_INPUT)。"""
    name = (raw_name or "").strip()
    if not 1 <= len(name) <= MAX_NAME_LEN or category not in CATEGORIES:
        raise BizError(400, "INVALID_INPUT")
    created_at = now_text()
    with write_transaction() as conn:
        cur = conn.execute(
            "INSERT INTO items (name, category, status, created_at)"
            " VALUES (?, ?, 'available', ?)",
            (name, category, created_at),
        )
    return cur.lastrowid


def get_item(item_id):
    """物品存在性单点查询（路由确认页与删除服务共用，PC-1：判定在 services）。"""
    return get_db().execute(
        "SELECT id, name, category, status FROM items WHERE id = ?",
        (item_id,),
    ).fetchone()


def delete_item(item_id):
    """删除物品（Story 3.2，FR-6 删除段），判定顺序固定（PC-9，真实 4xx）：

    ① 不存在 → 404 RESOURCE_NOT_FOUND；
    ② 存在未归还记录 → 409 ITEM_IN_BORROW，事务内尚无任何写入，
       直接抛异常触发回滚 → items/loans 逐字段不变（AC-3.2.1 危险拦截）；
    ③ 显式级联清理【已归还】历史记录（D-010：v1 无历史视图，孤儿记录
       只会产生空引用）——只删 returned_at IS NOT NULL，未归还记录即使
       竞态漏网也会被 ④ 的外键拦住而非静默消失；
    ④ DELETE items 删行。③④ 同一 BEGIN IMMEDIATE 事务（AC-3.2.3），
       中途任何异常整体回滚，不出现「物品删了历史还在」或反之的中间态。

    拒绝 ON DELETE CASCADE（D-020）：级联会静默绕过 ② 的业务拦截；
    显式删除 + 外键兜底把每次删除都变成可观测、可回滚的确定行为。
    """
    with write_transaction() as conn:
        if conn.execute(
            "SELECT id FROM items WHERE id = ?", (item_id,)
        ).fetchone() is None:
            raise BizError(404, "RESOURCE_NOT_FOUND")
        if conn.execute(
            "SELECT user_id FROM loans"
            " WHERE item_id = ? AND returned_at IS NULL LIMIT 1",
            (item_id,),
        ).fetchone() is not None:
            raise BizError(409, "ITEM_IN_BORROW")
        conn.execute(
            "DELETE FROM loans WHERE item_id = ? AND returned_at IS NOT NULL",
            (item_id,),
        )
        try:
            conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        except sqlite3.IntegrityError as exc:
            if _FK_LOANS_ITEM not in str(exc):
                raise
            # 业务拦截与物理兜底之间唯一可达的竞态：并发新借入刚插未提交。
            # 响应与 ② 逐字一致（D-016 同思路）；回滚由异常上抛触发，
            # ③ 已删除的历史记录随事务恢复，无任何变更残留（NFR-1.5）。
            raise BizError(409, "ITEM_IN_BORROW") from exc
