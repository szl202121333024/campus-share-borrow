"""管理员业务（Story 3.1，FR-6 新增段，PC-1、PC-9）。

校验口径（FR-6）：
- 名称去首尾空白后必须为 1–50 字符（长度真相 = config.MAX_NAME_LEN）；
- 类别必须是 book 或 equipment（严格字面值，不做大小写宽松）；
- 名称允许重复——一物一行（ADR-006），不做唯一校验。
任一校验失败统一抛 400 INVALID_INPUT（PC-9：真实 4xx，禁止 200+错误文案）。

写入 status 恒为 'available' 字面量（AR-4：'borrowed' 永不入库，CHECK 兜底）。
本故事只新增、不编辑、不删除、不停用（人类裁决：改名会使借阅历史失去名称快照
——v1 依 D-007 砍了快照字段，故 v1 不提供编辑；删除/停用/恢复属 Story 3.2~3.4）。
权限拦截不在本文件：403 由 routes/admin.py 的蓝图级守卫统一完成（D-012、PC-10），
业务代码内不得出现任何 role 判断。
"""

from config import MAX_NAME_LEN, BizError
from db import now_text, write_transaction

CATEGORIES = ("book", "equipment")


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
