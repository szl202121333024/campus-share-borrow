"""Story 3.3 停用物品 + Story 3.4 恢复上架（AC-3.3.1~3.3.7、AC-3.4.1~3.4.3、AC-3.4.8）。

这是 D-005 与 ADR-007 的最终验收场，三条不可妥协的口径：
1. **停用不中断借还（D-005）**：物品可在「在借」状态下停用；停用后借阅者仍能
   正常归还，归还只写 `loans`，绝不碰 `items.status`（它保持 `unavailable`）。
2. **恢复上架（ADR-007）**：`items.status` 可从 `unavailable` 改回 `available`；
   若此时仍有未归还记录，页面经 LEFT JOIN 渲染出的展示态仍是派生的「在借」，
   但底层 `items.status` 必须已经是 `available`——存储态与派生态各自回答不同问题。
3. **严格幂等**：重复停用 / 重复恢复一律 302 + 提示，绝不 409——状态机的迁移
   是幂等的，重复点击不是业务冲突。

数据构造口径遵循 epics.md「史诗独立性」条款：需要「在借记录」时用 SQL 直接
构造，不依赖 Epic 2 的借阅接口；仅在需要跨层复验时才调用真实 `/return`。

AC-3.4.4~3.4.7（四态组合矩阵、NFR-1.4 并发交叉比对）留在 Story 3.4 收口；
本文件只覆盖两个端点的行为与结构保证。
"""

import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

import db as db_module
from concurrency_kit import write_evidence_log
from config import ERROR_MESSAGES
from services.loans import get_remaining_quota

ADMIN = ("A001", "admin123456")
STUDENT = ("2024001", "stu123456")

SOURCE_ROOT = Path(__file__).resolve().parents[1]

# 种子数据里名称唯一的两件物品，便于按名称定位列表行
BOOK = "算法图解"
EQUIPMENT = "投影仪"

FLASH_BLOCK = re.compile(r'<div class="flash-messages"[^>]*>(.*?)</div>', re.S)
DOCSTRING = re.compile(r'""".*?"""', re.S)


# ---------------------------------------------------------------- 基础设施


def _login(client, credentials):
    return client.post(
        "/login",
        data={"student_id": credentials[0], "password": credentials[1]},
    )


def _login_admin(client):
    assert _login(client, ADMIN).status_code == 302


def _login_student(client):
    assert _login(client, STUDENT).status_code == 302


def _item_id_of(app, name):
    with app.app_context():
        row = db_module.get_db().execute(
            "SELECT id FROM items WHERE name = ?", (name,)
        ).fetchone()
    assert row is not None, name
    return row["id"]


def _item_status(app, item_id):
    with app.app_context():
        return db_module.get_db().execute(
            "SELECT status FROM items WHERE id = ?", (item_id,)
        ).fetchone()["status"]


def _set_status_directly(app, item_id, status):
    with app.app_context():
        db_module.get_db().execute(
            "UPDATE items SET status = ? WHERE id = ?", (status, item_id)
        )


def _items_snapshot(app):
    with app.app_context():
        rows = db_module.get_db().execute(
            "SELECT id, name, category, status, created_at FROM items ORDER BY id"
        ).fetchall()
    return [tuple(row) for row in rows]


def _loans_snapshot(app):
    with app.app_context():
        rows = db_module.get_db().execute(
            "SELECT id, item_id, user_id, borrowed_at, due_at, returned_at"
            " FROM loans ORDER BY id"
        ).fetchall()
    return [tuple(row) for row in rows]


def _insert_loan(app, item_id, user_pk, returned_at=None):
    """SQL 直接构造一条借阅记录（史诗独立性：不调 /borrow）。"""
    with app.app_context():
        db_module.get_db().execute(
            "INSERT INTO loans (item_id, user_id, borrowed_at, due_at, returned_at)"
            " VALUES (?, ?, '2026-11-01 10:00:00', '2026-11-08 10:00:00', ?)",
            (item_id, user_pk, returned_at),
        )


def _loan_id_of(app, item_id):
    with app.app_context():
        row = db_module.get_db().execute(
            "SELECT id FROM loans WHERE item_id = ? AND returned_at IS NULL",
            (item_id,),
        ).fetchone()
    assert row is not None
    return row["id"]


def _loan_returned_at(app, loan_id):
    with app.app_context():
        row = db_module.get_db().execute(
            "SELECT returned_at FROM loans WHERE id = ?", (loan_id,)
        ).fetchone()
    return None if row is None else row["returned_at"]


def _flash_of(client, path="/admin/items"):
    """取一次 PRG 落地页的 flash 文本（每个 GET 消费一次，不得重复 GET）。"""
    html = client.get(path).get_data(as_text=True)
    block = FLASH_BLOCK.search(html)
    return "" if block is None else block.group(1)


def _row_of(html, name):
    """从表格里取出含该物品名的那一行 HTML（断言列内容用）。"""
    body = html.split("<tbody>")[1].split("</tbody>")[0]
    rows = [chunk for chunk in body.split("<tr>") if name in chunk]
    assert len(rows) == 1, f"{name} 应恰好一行，实际 {len(rows)}"
    return rows[0]


def _student_page(client, query=None):
    return client.get("/items", query_string=query or {}).get_data(as_text=True)


def _service_source():
    return (SOURCE_ROOT / "services" / "admin.py").read_text(encoding="utf-8")


def _function_body(name):
    """取服务函数体并剥掉 docstring（结构断言只看代码，不看注释文字）。"""
    source = _service_source()
    start = source.index(f"def {name}(")
    rest = source[start:]
    match = re.search(r"\ndef [a-z_]+\(", rest)
    body = rest if match is None else rest[: match.start()]
    return DOCSTRING.sub("", body)


# ---------------------------------------------------------------- AC-3.3.1


def test_ac_3_3_1_disable_borrowed_item_keeps_active_loan(client, app):
    """在借物品可停用：302 +「已停用」，status 变 unavailable，未归还记录原样保留。"""
    _login_admin(client)
    item_id = _item_id_of(app, EQUIPMENT)
    _insert_loan(app, item_id, 1)
    loans_before = _loans_snapshot(app)

    response = client.post(f"/admin/items/{item_id}/unavailable")

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/admin/items"
    assert "已停用" in _flash_of(client)
    assert _item_status(app, item_id) == "unavailable"
    # 停用只写 items.status 一列：借阅记录逐字段不变，且在借记录仍在
    assert _loans_snapshot(app) == loans_before
    assert len(loans_before) == 1 and loans_before[0][5] is None
    assert _loan_returned_at(app, _loan_id_of(app, item_id)) is None


def test_ac_3_3_1_disable_never_borrowed_item_also_succeeds(client, app):
    """从未被借过的物品同样可停用（停用不依赖任何借阅事实）。"""
    _login_admin(client)
    item_id = _item_id_of(app, BOOK)

    response = client.post(f"/admin/items/{item_id}/unavailable")

    assert response.status_code == 302
    assert _item_status(app, item_id) == "unavailable"
    assert _loans_snapshot(app) == []


# ---------------------------------------------------------------- AC-3.3.2


def test_ac_3_3_2_disabled_item_hidden_from_students_but_visible_in_admin_list(client, app):
    """停用后学生端（列表 + 搜索）不可见；管理列表仍可见并标注「已停用」。"""
    _login_admin(client)
    item_id = _item_id_of(app, EQUIPMENT)
    assert client.post(f"/admin/items/{item_id}/unavailable").status_code == 302

    anonymous = app.test_client()
    # 搜索仍返回 200 空状态，不是 404
    search = anonymous.get("/items", query_string={"q": EQUIPMENT})
    assert search.status_code == 200
    assert EQUIPMENT not in search.get_data(as_text=True)
    assert EQUIPMENT not in _student_page(anonymous)

    admin_html = client.get("/admin/items").get_data(as_text=True)
    row = _row_of(admin_html, EQUIPMENT)
    assert "已停用" in row
    # 停用行给出的是「恢复上架」动作，不是再次「停用」
    assert f"/admin/items/{item_id}/available" in row
    assert f"/admin/items/{item_id}/unavailable" not in row


def test_ac_3_3_2_available_item_row_offers_disable_action(client, app):
    """未停用行给出「停用」动作：按钮随存储态切换，不随派生态（在借仍可停用）。"""
    _login_admin(client)
    item_id = _item_id_of(app, BOOK)
    _insert_loan(app, item_id, 1)  # 在借但未停用

    row = _row_of(client.get("/admin/items").get_data(as_text=True), BOOK)

    assert "在借" in row
    assert f"/admin/items/{item_id}/unavailable" in row
    assert f"/admin/items/{item_id}/available" not in row


# ---------------------------------------------------------------- AC-3.3.3


def test_ac_3_3_3_borrower_sees_disabled_loan_and_can_return_it(client, app):
    """D-005 用例 A 端到端：停用后借阅者 /my-loans 仍可见，归还仍 302，
    且归还只写 loans —— items.status 保持 unavailable（绝不回弹）。"""
    _login_admin(client)
    item_id = _item_id_of(app, EQUIPMENT)
    _insert_loan(app, item_id, 1)
    assert client.post(f"/admin/items/{item_id}/unavailable").status_code == 302
    loan_id = _loan_id_of(app, item_id)
    items_before = _items_snapshot(app)

    borrower = app.test_client()
    _login_student(borrower)
    my_loans = borrower.get("/my-loans")
    assert my_loans.status_code == 200
    assert EQUIPMENT in my_loans.get_data(as_text=True)

    response = borrower.post(f"/return/{loan_id}")

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/my-loans"
    assert "已归还" in _flash_of(borrower, "/my-loans")
    assert _loan_returned_at(app, loan_id) is not None
    # 归还绝不改物品状态：停用物品归还后仍停用（D-005 + D-014）
    assert _item_status(app, item_id) == "unavailable"
    assert _items_snapshot(app) == items_before
    # 归还后学生端仍然看不到（停用优先于「可借」）
    assert EQUIPMENT not in _student_page(borrower)


def test_ac_3_3_3_return_releases_quota_of_disabled_loan(client, app):
    """停用不冻结归还：归还后额度立即释放（FR-4/FR-5 交叉点）。"""
    _login_admin(client)
    item_id = _item_id_of(app, EQUIPMENT)
    _insert_loan(app, item_id, 1)
    assert client.post(f"/admin/items/{item_id}/unavailable").status_code == 302

    borrower = app.test_client()
    _login_student(borrower)
    with app.app_context():
        assert get_remaining_quota(1) == 2
    assert borrower.post(f"/return/{_loan_id_of(app, item_id)}").status_code == 302
    with app.app_context():
        assert get_remaining_quota(1) == 3


# ---------------------------------------------------------------- AC-3.3.4


def test_ac_3_3_4_repeat_disable_is_idempotent_success(client, app):
    """重复停用：再次 302 +「已停用」，绝不 409，status 保持 unavailable。"""
    _login_admin(client)
    item_id = _item_id_of(app, EQUIPMENT)
    assert client.post(f"/admin/items/{item_id}/unavailable").status_code == 302

    second = client.post(f"/admin/items/{item_id}/unavailable")

    assert second.status_code == 302
    assert urlparse(second.headers["Location"]).path == "/admin/items"
    landing = client.get(second.headers["Location"]).get_data(as_text=True)
    assert "已停用" in landing
    assert "ITEM_UNAVAILABLE" not in landing and "409" not in landing
    assert _item_status(app, item_id) == "unavailable"


def test_ac_3_3_4_repeat_disable_keeps_active_loan_untouched(client, app):
    """幂等重放不得有副作用：多次停用后 items/loans 快照仍逐字段不变。"""
    _login_admin(client)
    item_id = _item_id_of(app, EQUIPMENT)
    _insert_loan(app, item_id, 1)
    assert client.post(f"/admin/items/{item_id}/unavailable").status_code == 302
    items_before = _items_snapshot(app)
    loans_before = _loans_snapshot(app)

    for _ in range(3):
        assert client.post(f"/admin/items/{item_id}/unavailable").status_code == 302

    assert _items_snapshot(app) == items_before
    assert _loans_snapshot(app) == loans_before


# ---------------------------------------------------------------- AC-3.3.5


def test_ac_3_3_5_check_constraint_rejects_borrowed_storage_value(app):
    """AR-4：直接写 'borrowed' 被 CHECK 约束拒绝（存储态只有两个取值）。"""
    item_id = _item_id_of(app, BOOK)

    with app.app_context():
        with pytest.raises(sqlite3.IntegrityError) as excinfo:
            db_module.get_db().execute(
                "UPDATE items SET status = 'borrowed' WHERE id = ?", (item_id,)
            )
    assert "CHECK constraint failed" in str(excinfo.value)
    assert _item_status(app, item_id) == "available"


def test_ac_3_3_5_disable_sql_only_writes_unavailable_literal():
    """停用路径的 SQL 只写入 'unavailable' 字面量；全项目 UPDATE items 恰两处。"""
    disable_body = _function_body("set_unavailable")
    assert "UPDATE items SET status = 'unavailable' WHERE id = ?" in disable_body
    assert "borrowed" not in disable_body.lower()

    restore_body = _function_body("set_available")
    assert "UPDATE items SET status = 'available' WHERE id = ?" in restore_body
    assert "borrowed" not in restore_body.lower()

    hits = []
    for subdir in ("services", "routes"):
        for path in sorted((SOURCE_ROOT / subdir).glob("*.py")):
            # 剥掉 docstring：注释里提到 `grep "UPDATE items"` 不算一条写语句
            text = DOCSTRING.sub("", path.read_text(encoding="utf-8"))
            for match in re.finditer(r"UPDATE\s+items[^\n]*", text, re.I):
                hits.append((f"{subdir}/{path.name}", match.group(0)))
    assert [origin for origin, _sql in hits] == ["services/admin.py", "services/admin.py"]
    assert all("borrowed" not in sql.lower() for _origin, sql in hits)


# ---------------------------------------------------------------- AC-3.3.6


def test_ac_3_3_6_student_cannot_disable(client, app):
    _login_student(client)
    item_id = _item_id_of(app, EQUIPMENT)
    items_before = _items_snapshot(app)

    response = client.post(f"/admin/items/{item_id}/unavailable")

    assert response.status_code == 403
    body = response.get_data(as_text=True)
    assert "FORBIDDEN" in body
    assert ERROR_MESSAGES["FORBIDDEN"] in body
    assert _items_snapshot(app) == items_before


def test_ac_3_3_6_anonymous_disable_redirects_to_login(client, app):
    item_id = _item_id_of(app, EQUIPMENT)
    items_before = _items_snapshot(app)

    response = client.post(f"/admin/items/{item_id}/unavailable")

    assert response.status_code == 302
    location = urlparse(response.headers["Location"])
    assert location.path == "/login"
    assert parse_qs(location.query)["next"] == [
        f"/admin/items/{item_id}/unavailable"
    ]
    assert _items_snapshot(app) == items_before


# ---------------------------------------------------------------- AC-3.3.7


def test_ac_3_3_7_disabled_loan_still_counts_toward_quota(client, app):
    """停用不释放额度：停用物品上的未归还记录照常计入在借数（FR-5）。"""
    _login_admin(client)
    item_id = _item_id_of(app, EQUIPMENT)
    _insert_loan(app, item_id, 1)
    with app.app_context():
        assert get_remaining_quota(1) == 2

    assert client.post(f"/admin/items/{item_id}/unavailable").status_code == 302

    with app.app_context():
        assert get_remaining_quota(1) == 2
    borrower = app.test_client()
    _login_student(borrower)
    assert "已借 1 / 3" in borrower.get("/my-loans").get_data(as_text=True)


# ---------------------------------------------------------------- AC-3.4.1


def test_ac_3_4_1_restore_returns_item_to_student_view(client, app):
    """恢复上架：302 +「已恢复上架」，status 变 available，重新出现在列表与搜索。"""
    _login_admin(client)
    item_id = _item_id_of(app, EQUIPMENT)
    assert client.post(f"/admin/items/{item_id}/unavailable").status_code == 302
    assert EQUIPMENT not in _student_page(app.test_client())

    response = client.post(f"/admin/items/{item_id}/available")

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/admin/items"
    assert "已恢复上架" in _flash_of(client)
    assert _item_status(app, item_id) == "available"

    anonymous = app.test_client()
    assert EQUIPMENT in _student_page(anonymous)
    assert EQUIPMENT in _student_page(anonymous, {"q": EQUIPMENT})
    # 恢复后管理行改回「停用」动作
    row = _row_of(client.get("/admin/items").get_data(as_text=True), EQUIPMENT)
    assert f"/admin/items/{item_id}/unavailable" in row


# ---------------------------------------------------------------- AC-3.4.2


def test_ac_3_4_2_repeat_restore_is_idempotent_success(client, app):
    """重复恢复：已是 available 时再次恢复仍 302 +「已恢复上架」，不报错。"""
    _login_admin(client)
    item_id = _item_id_of(app, BOOK)
    assert _item_status(app, item_id) == "available"

    first = client.post(f"/admin/items/{item_id}/available")
    second = client.post(f"/admin/items/{item_id}/available")

    assert first.status_code == second.status_code == 302
    landing = client.get(second.headers["Location"]).get_data(as_text=True)
    assert "已恢复上架" in landing
    assert "ITEM_UNAVAILABLE" not in landing and "FORBIDDEN" not in landing
    assert _item_status(app, item_id) == "available"


def test_ac_3_4_2_disable_restore_cycle_is_repeatable(client, app):
    """停用 ↔ 恢复可任意次往返，每步都 302，状态跟随最后一次动作。"""
    _login_admin(client)
    item_id = _item_id_of(app, EQUIPMENT)

    for action, expected in (
        ("unavailable", "unavailable"),
        ("available", "available"),
        ("unavailable", "unavailable"),
        ("available", "available"),
    ):
        assert client.post(f"/admin/items/{item_id}/{action}").status_code == 302
        assert _item_status(app, item_id) == expected


# ---------------------------------------------------------------- AC-3.4.3（D-005 用例 B）


def test_ac_3_4_3_restore_while_borrowed_keeps_derived_borrowed_state(client, app):
    """D-005 用例 B：存储态 available + 派生态 在借 同时成立。

    该物品仍有一条未归还记录，管理员恢复上架后：
    - 底层 `items.status` 必须是 'available'（存储态听管理员的）；
    - 学生列表经 LEFT JOIN 派生出 'borrowed'，显示「在借」而不是「可借」；
    - 借阅记录一条不少、未归还时间戳仍为空（恢复不修改借阅事实）。
    """
    _login_admin(client)
    item_id = _item_id_of(app, EQUIPMENT)
    _insert_loan(app, item_id, 1)
    assert client.post(f"/admin/items/{item_id}/unavailable").status_code == 302
    loans_before = _loans_snapshot(app)

    response = client.post(f"/admin/items/{item_id}/available")

    assert response.status_code == 302
    # 1) 存储态由管理员改写：既不是「仍然停用」，也不是任何 borrowed 存储值
    assert _item_status(app, item_id) == "available"
    # 2) 派生态由 loans 算出：物品回到学生列表，但显示「在借」
    anonymous = app.test_client()
    html = _student_page(anonymous)
    assert EQUIPMENT in html
    row = _row_of(html, EQUIPMENT)
    assert "在借" in row
    assert "可借" not in row
    # 3) 借阅事实未被恢复动作触碰（D-005：恢复上架不代还、不清记录）
    assert _loans_snapshot(app) == loans_before
    assert _loan_returned_at(app, _loan_id_of(app, item_id)) is None
    # 4) 管理列表同理：显示「在借」并给出在借人，且不再标注「已停用」
    admin_row = _row_of(client.get("/admin/items").get_data(as_text=True), EQUIPMENT)
    assert "在借" in admin_row and "林晓" in admin_row
    assert "已停用" not in admin_row


def test_ac_3_4_3_restore_then_return_derives_available(client, app):
    """恢复上架后借阅者归还：派生态从「在借」回到「可借」，存储态不动。"""
    _login_admin(client)
    item_id = _item_id_of(app, EQUIPMENT)
    _insert_loan(app, item_id, 1)
    assert client.post(f"/admin/items/{item_id}/unavailable").status_code == 302
    assert client.post(f"/admin/items/{item_id}/available").status_code == 302

    borrower = app.test_client()
    _login_student(borrower)
    assert borrower.post(f"/return/{_loan_id_of(app, item_id)}").status_code == 302

    assert _item_status(app, item_id) == "available"
    row = _row_of(_student_page(borrower), EQUIPMENT)
    assert "可借" in row and "在借" not in row


# ---------------------------------------------------------------- AC-3.4.8


def test_ac_3_4_8_student_cannot_restore(client, app):
    _login_student(client)
    item_id = _item_id_of(app, EQUIPMENT)
    _set_status_directly(app, item_id, "unavailable")
    items_before = _items_snapshot(app)

    response = client.post(f"/admin/items/{item_id}/available")

    assert response.status_code == 403
    assert "FORBIDDEN" in response.get_data(as_text=True)
    assert _items_snapshot(app) == items_before


def test_ac_3_4_8_anonymous_restore_redirects_to_login(client, app):
    item_id = _item_id_of(app, EQUIPMENT)
    _set_status_directly(app, item_id, "unavailable")
    items_before = _items_snapshot(app)

    response = client.post(f"/admin/items/{item_id}/available")

    assert response.status_code == 302
    location = urlparse(response.headers["Location"])
    assert location.path == "/login"
    assert parse_qs(location.query)["next"] == [f"/admin/items/{item_id}/available"]
    assert _items_snapshot(app) == items_before


# ---------------------------------------------------------------- 边界与结构


def test_missing_item_returns_404_on_both_transitions(client, app):
    _login_admin(client)
    items_before = _items_snapshot(app)
    loans_before = _loans_snapshot(app)

    for action in ("unavailable", "available"):
        response = client.post(f"/admin/items/99999/{action}")
        assert response.status_code == 404, action
        assert "RESOURCE_NOT_FOUND" in response.get_data(as_text=True)

    assert _items_snapshot(app) == items_before
    assert _loans_snapshot(app) == loans_before


def test_transitions_never_touch_loans_sql():
    """结构保证：两条状态迁移的 SQL 里没有 loans ——「归还后仍停用」是结构性的。"""
    for name in ("set_unavailable", "set_available"):
        body = _function_body(name)
        assert "loans" not in body.lower(), name
        assert "UPDATE items SET status = '" in body, name


def test_transition_functions_use_write_transaction():
    """PC-4：两条迁移都走全项目唯一写事务原语（BEGIN IMMEDIATE）。"""
    for name in ("set_unavailable", "set_available"):
        body = _function_body(name)
        assert "with write_transaction() as conn:" in body, name
        assert body.index("with write_transaction()") < body.index("UPDATE items"), name


def test_no_loans_mutation_across_disable_and_restore(client, app):
    """停用→恢复一整圈后 loans 表逐字段不变：状态迁移对借阅事实零副作用。"""
    _login_admin(client)
    item_id = _item_id_of(app, EQUIPMENT)
    _insert_loan(app, item_id, 1)
    _insert_loan(app, item_id, 2, returned_at="2026-10-20 10:00:00")
    loans_before = _loans_snapshot(app)

    assert client.post(f"/admin/items/{item_id}/unavailable").status_code == 302
    assert client.post(f"/admin/items/{item_id}/available").status_code == 302
    assert client.post(f"/admin/items/{item_id}/unavailable").status_code == 302

    assert _loans_snapshot(app) == loans_before


# ---------------------------------------------------------------- 并发幂等（20 轮）


def _race_state_change(app, action, item_id, reset_status, rounds=20):
    """20 轮真并发：两个管理员会话（各自独立 client）同时 POST 同一次状态迁移。

    并发形态与 AC-2.2.9 同脚手架：threading.Barrier(2) + 各自独立会话，
    每轮先由直连 SQL 把状态复位到 `reset_status`，再让两个会话同时提交。
    """
    log_lines = []
    for round_no in range(1, rounds + 1):
        _set_status_directly(app, item_id, reset_status)
        barrier = threading.Barrier(2)
        results, errors, started_at = {}, {}, {}

        def attempt(tag):
            own_client = app.test_client()
            _login_admin(own_client)
            try:
                barrier.wait(timeout=15)
                started_at[tag] = time.perf_counter()
                results[tag] = own_client.post(
                    f"/admin/items/{item_id}/{action}"
                ).status_code
            except BaseException as exc:  # noqa: BLE001 - 线程内异常必须回传主线程
                errors[tag] = repr(exc)

        threads = [threading.Thread(target=attempt, args=(tag,)) for tag in ("a", "b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        assert errors == {}, (round_no, errors)
        assert sorted(results.values()) == [302, 302], (round_no, results)
        spread_ms = (max(started_at.values()) - min(started_at.values())) * 1000
        log_lines.append(
            f"round {round_no:02d}: a={results['a']} b={results['b']}"
            f" | barrier 释放间隔={spread_ms:.2f}ms"
            f" | status={_item_status(app, item_id)}"
        )
    return log_lines


def test_concurrent_double_disable_is_idempotent_20_rounds(app, client):
    """并发重复停用：20 轮两个会话都拿 302（无 409），status 恒为 unavailable。"""
    _login_admin(client)
    item_id = _item_id_of(app, EQUIPMENT)
    _insert_loan(app, item_id, 1)
    loans_before = _loans_snapshot(app)

    lines = [
        f"# Story 3.3 / 并发重复停用幂等真实日志  生成于 {datetime.now():%Y-%m-%d %H:%M:%S}",
        "启动命令: python -m pytest tests/test_admin_state.py -v -k concurrent",
        "并发方式: threading.Barrier(2) + 2 线程 + 各自独立 Flask test_client 与会话（管理员同一账号）",
        "实验设定: 目标物品有 1 条未归还记录；两点同时 POST /admin/items/<id>/unavailable",
        "-" * 72,
    ]
    lines += _race_state_change(app, "unavailable", item_id, "available")
    write_evidence_log("concurrency-story33-double-disable-20-rounds.log", lines)
    assert _item_status(app, item_id) == "unavailable"
    assert _loans_snapshot(app) == loans_before


def test_concurrent_double_restore_is_idempotent_20_rounds(app, client):
    """并发重复恢复：20 轮两个会话都拿 302（无 409），status 恒为 available。"""
    _login_admin(client)
    item_id = _item_id_of(app, BOOK)
    _insert_loan(app, item_id, 1)
    loans_before = _loans_snapshot(app)

    lines = [
        f"# Story 3.4 / 并发重复恢复上架幂等真实日志  生成于 {datetime.now():%Y-%m-%d %H:%M:%S}",
        "启动命令: python -m pytest tests/test_admin_state.py -v -k concurrent",
        "并发方式: threading.Barrier(2) + 2 线程 + 各自独立 Flask test_client 与会话（管理员同一账号）",
        "实验设定: 目标物品有 1 条未归还记录；两点同时 POST /admin/items/<id>/available",
        "-" * 72,
    ]
    lines += _race_state_change(app, "available", item_id, "unavailable")
    write_evidence_log("concurrency-story34-double-restore-20-rounds.log", lines)

    assert _item_status(app, item_id) == "available"
    assert _loans_snapshot(app) == loans_before
    # 仍有未归还记录 → 派生态仍是「在借」
    row = _row_of(_student_page(app.test_client()), BOOK)
    assert "在借" in row
