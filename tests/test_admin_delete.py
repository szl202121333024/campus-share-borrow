"""Story 3.2：删除物品（AC-3.2.1 ~ 3.2.7 + D-010/D-020 白盒兜底 + 并发边界）。

数据构造口径遵循 epics.md「史诗独立性」条款：需要「在借/已归还记录」时用 SQL
直接构造，不依赖 Epic 2 的借阅接口；仅「删除 vs 借阅」对抗实验调用真实
``POST /borrow`` 以制造业务竞态。并发形态复用 tests/concurrency_kit.py
（threaded 真实服务器 + barrier + 各自独立 TCP 连接），与 Story 2.3/2.4/2.5
同一脚手架。

三个不可妥协的断言（人类开工指令）：
1. 有未归还记录 → 409 ITEM_IN_BORROW，且 items/loans 逐字段快照不变；
2. 无在借时，清理已归还历史与删除物品在同一 BEGIN IMMEDIATE 事务内完成；
3. 外键不带 ON DELETE CASCADE，物理兜底由数据库拒绝（白盒直删证明）。
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

import db as db_module
import services.admin as admin_service
from config import ERROR_MESSAGES, BizError
from concurrency_kit import (
    direct_connect,
    login_over_http,
    race_request,
    start_threaded_server,
)

ADMIN = ("A001", "admin123456")
STUDENT = ("2024001", "stu123456")
SOURCE_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = SOURCE_ROOT / "_bmad-output" / "implementation-artifacts"
ROUNDS = 20


# ---------------------------------------------------------------- 基础设施


def _login(client, student_id, password):
    return client.post(
        "/login", data={"student_id": student_id, "password": password}
    )


def _login_admin(client):
    assert _login(client, *ADMIN).status_code == 302


def _item_id_of(app, name):
    with app.app_context():
        row = db_module.get_db().execute(
            "SELECT id FROM items WHERE name = ?", (name,)
        ).fetchone()
    return None if row is None else row["id"]


def _items_snapshot(app):
    """items 全字段快照：409 拦截必须做到「数据库零变更」，不是「行数不变」。"""
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


def _insert_loan(app, item_id, user_pk, returned_at):
    """SQL 直接构造一条借阅记录（史诗独立性：不调 /borrow）。"""
    with app.app_context():
        db_module.get_db().execute(
            "INSERT INTO loans (item_id, user_id, borrowed_at, due_at, returned_at)"
            " VALUES (?, ?, '2026-10-20 10:00:00', '2026-10-27 10:00:00', ?)",
            (item_id, user_pk, returned_at),
        )


def _seed_returned_history(app, item_id, user_pks=(1, 1, 1)):
    for user_pk in user_pks:
        _insert_loan(app, item_id, user_pk, "2026-10-09 10:00:00")


def _count(sql, params=()):
    conn = direct_connect()
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


def _direct_execute(sql, params=()):
    conn = direct_connect()
    try:
        conn.execute(sql, params)
    finally:
        conn.close()


def _direct_insert_item(name, status="available"):
    conn = direct_connect()
    try:
        cursor = conn.execute(
            "INSERT INTO items (name, category, status, created_at)"
            " VALUES (?, 'equipment', ?, '2026-11-10 09:00:00')",
            (name, status),
        )
        return cursor.lastrowid
    finally:
        conn.close()


def _direct_insert_loan(item_id, user_pk=2, returned_at=None):
    conn = direct_connect()
    try:
        conn.execute(
            "INSERT INTO loans (item_id, user_id, borrowed_at, due_at, returned_at)"
            " VALUES (?, ?, '2026-10-01 10:00:00', '2026-10-08 10:00:00', ?)",
            (item_id, user_pk, returned_at),
        )
    finally:
        conn.close()


def _direct_connect_with_fk():
    """与生产 get_db() 同口径：显式开启外键（PC-2 的 PRAGMA 之一）。"""
    conn = direct_connect()
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _write_log(filename, lines):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")


class _EmptyCursor:
    def fetchone(self):
        return None


class _BlindToActiveLoan:
    """模拟「业务拦截被绕过」的唯一竞态：在借存在性查询返回空。"""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        if "returned_at IS NULL LIMIT 1" in sql:
            return _EmptyCursor()
        return self._conn.execute(sql, params)


class _ExplodingItemDelete:
    """在 DELETE loans 之后、DELETE items 之前注入异常（AC-3.2.3）。"""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        if "DELETE FROM items" in sql:
            raise RuntimeError("注入：物品删除前崩溃")
        return self._conn.execute(sql, params)


class _CheckConstraintBoomOnItemDelete:
    """非外键的 IntegrityError：必须原样上抛，不得伪装成 409（ADR-008）。"""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        if "DELETE FROM items" in sql:
            raise sqlite3.IntegrityError("CHECK constraint failed: status")
        return self._conn.execute(sql, params)


def _transaction_with(wrapper_cls):
    """把真实 BEGIN IMMEDIATE 事务里的连接换成受控替身（提交/回滚仍是真连接）。"""
    real_write_transaction = db_module.write_transaction

    @contextmanager
    def transaction():
        with real_write_transaction() as conn:
            yield wrapper_cls(conn)

    return transaction


# ---------------------------------------------------------------- AC-3.2.1 危险拦截


def test_ac_3_2_1_active_loan_blocks_delete_without_any_mutation(client, app):
    _login_admin(client)
    item_id = _item_id_of(app, "投影仪")
    _insert_loan(app, item_id, 1, returned_at=None)
    items_before = _items_snapshot(app)
    loans_before = _loans_snapshot(app)

    response = client.post(f"/admin/items/{item_id}/delete")

    assert response.status_code == 409
    html = response.get_data(as_text=True)
    assert "ITEM_IN_BORROW" in html
    assert ERROR_MESSAGES["ITEM_IN_BORROW"] in html
    assert _items_snapshot(app) == items_before
    assert _loans_snapshot(app) == loans_before


def test_ac_3_2_1_mixed_history_is_not_partially_cleaned(client, app):
    """在借 + 已归还混存：先拦截，绝不能先把已归还记录清掉再发现删不了。"""
    _login_admin(client)
    item_id = _item_id_of(app, "三体")
    _seed_returned_history(app, item_id, (1, 1))
    _insert_loan(app, item_id, 2, returned_at=None)
    items_before = _items_snapshot(app)
    loans_before = _loans_snapshot(app)
    assert len(loans_before) == 3

    response = client.post(f"/admin/items/{item_id}/delete")

    assert response.status_code == 409
    assert "ITEM_IN_BORROW" in response.get_data(as_text=True)
    assert _items_snapshot(app) == items_before
    assert _loans_snapshot(app) == loans_before
    assert _count(
        "SELECT COUNT(*) FROM loans WHERE item_id = ? AND returned_at IS NOT NULL",
        (item_id,),
    ) == 2


def test_ac_3_2_1_unavailable_item_with_active_loan_still_409(client, app):
    """停用不构成删除许可：只要有人在借，一律 409（D-003/D-010 边界）。"""
    _login_admin(client)
    item_id = _item_id_of(app, "蓝牙音箱")
    with app.app_context():
        db_module.get_db().execute(
            "UPDATE items SET status = 'unavailable' WHERE id = ?", (item_id,)
        )
    _insert_loan(app, item_id, 1, returned_at=None)
    items_before = _items_snapshot(app)
    loans_before = _loans_snapshot(app)

    response = client.post(f"/admin/items/{item_id}/delete")

    assert response.status_code == 409
    assert _items_snapshot(app) == items_before
    assert _loans_snapshot(app) == loans_before


# ---------------------------------------------------------------- AC-3.2.2 同事务级联清理


def test_ac_3_2_2_returned_history_is_cascade_cleaned(client, app):
    _login_admin(client)
    item_id = _item_id_of(app, "活着")
    _seed_returned_history(app, item_id, (1, 2, 1))
    assert _count("SELECT COUNT(*) FROM loans WHERE item_id = ?", (item_id,)) == 3

    response = client.post(f"/admin/items/{item_id}/delete")

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/admin/items"
    landing = client.get("/admin/items")
    assert "已删除" in landing.get_data(as_text=True)
    assert _item_id_of(app, "活着") is None
    assert _count("SELECT COUNT(*) FROM loans WHERE item_id = ?", (item_id,)) == 0


def test_ac_3_2_2_delete_only_cleans_target_items_history(client, app):
    """级联清理必须带 item_id 作用域：不能把别的物品的历史一起删掉。"""
    _login_admin(client)
    target_id = _item_id_of(app, "活着")
    other_id = _item_id_of(app, "算法图解")
    _seed_returned_history(app, target_id, (1,))
    _seed_returned_history(app, other_id, (1, 2))

    response = client.post(f"/admin/items/{target_id}/delete")

    assert response.status_code == 302
    assert _count("SELECT COUNT(*) FROM loans WHERE item_id = ?", (target_id,)) == 0
    assert _count("SELECT COUNT(*) FROM loans WHERE item_id = ?", (other_id,)) == 2
    assert _item_id_of(app, "算法图解") == other_id


def test_boundary_unavailable_item_without_loans_deletes_cleanly(client, app):
    """Epic 3 四边界之一：停用但无借阅的物品可删（409 只针对在借，与停用无关）。"""
    _login_admin(client)
    item_id = _item_id_of(app, "蓝牙音箱")
    with app.app_context():
        db_module.get_db().execute(
            "UPDATE items SET status = 'unavailable' WHERE id = ?", (item_id,)
        )

    response = client.post(f"/admin/items/{item_id}/delete")

    assert response.status_code == 302
    assert _item_id_of(app, "蓝牙音箱") is None
    assert _count("SELECT COUNT(*) FROM loans WHERE item_id = ?", (item_id,)) == 0


def test_boundary_never_borrowed_item_deletes_cleanly(client, app):
    """Epic 3 四边界之一：从未被借过的物品可直接删除，无 loans 残留。"""
    _login_admin(client)
    item_id = _item_id_of(app, "热熔胶枪")
    assert _count("SELECT COUNT(*) FROM loans WHERE item_id = ?", (item_id,)) == 0

    response = client.post(f"/admin/items/{item_id}/delete")

    assert response.status_code == 302
    assert _item_id_of(app, "热熔胶枪") is None
    assert _count("SELECT COUNT(*) FROM loans WHERE item_id = ?", (item_id,)) == 0


# ---------------------------------------------------------------- AC-3.2.3 事务原子性


def test_ac_3_2_3_exception_between_cascade_and_item_delete_rolls_back(app, monkeypatch):
    item_id = _item_id_of(app, "三体")
    _seed_returned_history(app, item_id, (1, 1))
    items_before = _items_snapshot(app)
    loans_before = _loans_snapshot(app)

    monkeypatch.setattr(
        admin_service, "write_transaction", _transaction_with(_ExplodingItemDelete)
    )

    with app.app_context():
        with pytest.raises(RuntimeError):
            admin_service.delete_item(item_id)

    # 中间态绝不残留：物品仍在、已归还记录条数不变、逐字段与快照一致
    assert _items_snapshot(app) == items_before
    assert _loans_snapshot(app) == loans_before
    assert _count("SELECT COUNT(*) FROM loans WHERE item_id = ?", (item_id,)) == 2


# ---------------------------------------------------------------- AC-3.2.4 不存在 404


def test_ac_3_2_4_missing_item_returns_404(client, app):
    _login_admin(client)
    items_before = _items_snapshot(app)
    loans_before = _loans_snapshot(app)

    response = client.post("/admin/items/99999/delete")

    assert response.status_code == 404
    assert "RESOURCE_NOT_FOUND" in response.get_data(as_text=True)
    assert _items_snapshot(app) == items_before
    assert _loans_snapshot(app) == loans_before


# ---------------------------------------------------------------- AC-3.2.5 外键不带 CASCADE


def test_ac_3_2_5_item_foreign_key_is_not_cascade(app):
    with app.app_context():
        rows = db_module.get_db().execute("PRAGMA foreign_key_list('loans')").fetchall()
    item_fk = [row for row in rows if row["table"] == "items"]
    assert len(item_fk) == 1
    # SQLite 默认 NO ACTION：没有隐式级联，删物品会被外键拒绝
    assert item_fk[0]["on_delete"].upper() == "NO ACTION"


def test_ac_3_2_5_schema_and_delete_path_have_no_implicit_cascade():
    schema = (SOURCE_ROOT / "db.py").read_text(encoding="utf-8")
    assert "ON DELETE CASCADE" not in schema.upper()

    source = (SOURCE_ROOT / "services" / "admin.py").read_text(encoding="utf-8")
    body = source[source.index("def delete_item") :]
    # 显式清理 + 显式删物品，顺序固定，且都在 write_transaction() 内
    assert "DELETE FROM loans WHERE item_id = ? AND returned_at IS NOT NULL" in body
    assert "DELETE FROM items WHERE id = ?" in body
    assert body.index("with write_transaction()") < body.index("DELETE FROM loans")
    assert body.index("DELETE FROM loans") < body.index("DELETE FROM items")


def test_app_connection_enables_foreign_keys(app):
    """生产连接必须开启外键，否则「外键兜底」只是一句注释。"""
    with app.app_context():
        assert db_module.get_db().execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_fk_backstop_direct_delete_of_active_item_raises(app):
    """D-020/D-021 同思路：绕过业务层直删在借物品，数据库必须拒绝。"""
    item_id = _item_id_of(app, "热熔胶枪")
    _insert_loan(app, item_id, 1, returned_at=None)

    conn = _direct_connect_with_fk()
    try:
        with pytest.raises(sqlite3.IntegrityError) as excinfo:
            conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        assert "FOREIGN KEY constraint failed" in str(excinfo.value)
        conn.rollback()
        assert conn.execute(
            "SELECT COUNT(*) FROM items WHERE id = ?", (item_id,)
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM loans WHERE item_id = ? AND returned_at IS NULL",
            (item_id,),
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_fk_backstop_maps_to_item_in_borrow_and_restores_history(app, monkeypatch):
    """业务拦截与物理兜底之间唯一可达的竞态：查询漏网时外键兜底，响应与 ② 一致。"""
    item_id = _item_id_of(app, "三体")
    _seed_returned_history(app, item_id, (1,))
    _insert_loan(app, item_id, 2, returned_at=None)
    items_before = _items_snapshot(app)
    loans_before = _loans_snapshot(app)

    monkeypatch.setattr(
        admin_service, "write_transaction", _transaction_with(_BlindToActiveLoan)
    )

    with app.app_context():
        with pytest.raises(BizError) as excinfo:
            admin_service.delete_item(item_id)

    assert excinfo.value.status_code == 409
    assert excinfo.value.error_code == "ITEM_IN_BORROW"
    # 事务回滚：被删的已归还历史随事务恢复，无任何残留
    assert _items_snapshot(app) == items_before
    assert _loans_snapshot(app) == loans_before


def test_non_fk_integrity_error_is_not_disguised_as_409(app, monkeypatch):
    """ADR-008：只映射外键那一种 IntegrityError，其余原样上抛。"""
    item_id = _item_id_of(app, "算法图解")
    items_before = _items_snapshot(app)
    loans_before = _loans_snapshot(app)

    monkeypatch.setattr(
        admin_service,
        "write_transaction",
        _transaction_with(_CheckConstraintBoomOnItemDelete),
    )

    with app.app_context():
        with pytest.raises(sqlite3.IntegrityError) as excinfo:
            admin_service.delete_item(item_id)

    assert not isinstance(excinfo.value, BizError)
    assert "CHECK constraint failed" in str(excinfo.value)
    assert _items_snapshot(app) == items_before
    assert _loans_snapshot(app) == loans_before


# ---------------------------------------------------------------- AC-3.2.6 确认页


def test_ac_3_2_6_confirm_page_renders_without_deleting(client, app):
    _login_admin(client)
    item_id = _item_id_of(app, "算法图解")
    _seed_returned_history(app, item_id, (1,))
    items_before = _items_snapshot(app)
    loans_before = _loans_snapshot(app)

    response = client.get(f"/admin/items/{item_id}/delete")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    html = response.get_data(as_text=True)
    assert "算法图解" in html
    assert "确认删除" in html
    assert 'method="post"' in html
    assert _items_snapshot(app) == items_before
    assert _loans_snapshot(app) == loans_before


def test_ac_3_2_6_get_delete_path_never_deletes(client, app):
    """写操作只接受 POST：浏览器地址栏 GET 再多次也不产生删除。"""
    _login_admin(client)
    item_id = _item_id_of(app, "蓝牙音箱")
    items_before = _items_snapshot(app)

    for _ in range(2):
        assert client.get(f"/admin/items/{item_id}/delete").status_code == 200
        assert _items_snapshot(app) == items_before

    assert client.post(f"/admin/items/{item_id}/delete").status_code == 302
    assert _item_id_of(app, "蓝牙音箱") is None


def test_ac_3_2_6_confirm_page_of_missing_item_is_404(client):
    _login_admin(client)
    response = client.get("/admin/items/99999/delete")
    assert response.status_code == 404
    assert "RESOURCE_NOT_FOUND" in response.get_data(as_text=True)


# ---------------------------------------------------------------- AC-3.2.7 权限边界


def test_ac_3_2_7_student_get_and_post_are_forbidden_with_untouched_data(client, app):
    _login(client, *STUDENT)
    item_id = _item_id_of(app, "活着")
    items_before = _items_snapshot(app)
    loans_before = _loans_snapshot(app)

    for response in (
        client.post(f"/admin/items/{item_id}/delete"),
        client.get(f"/admin/items/{item_id}/delete"),
    ):
        assert response.status_code == 403
        assert "FORBIDDEN" in response.get_data(as_text=True)
    assert _items_snapshot(app) == items_before
    assert _loans_snapshot(app) == loans_before


def test_ac_3_2_7_anonymous_get_and_post_redirect_to_login(client, app):
    item_id = 1
    items_before = _items_snapshot(app)
    loans_before = _loans_snapshot(app)

    for response in (
        client.post(f"/admin/items/{item_id}/delete"),
        client.get(f"/admin/items/{item_id}/delete"),
    ):
        assert response.status_code == 302
        location = urlparse(response.headers["Location"])
        assert location.path == "/login"
        assert parse_qs(location.query)["next"] == [
            f"/admin/items/{item_id}/delete"
        ]
    assert _items_snapshot(app) == items_before
    assert _loans_snapshot(app) == loans_before


# ---------------------------------------------------------------- 串行边界


def test_second_serial_delete_is_404(client, app):
    _login_admin(client)
    item_id = _item_id_of(app, "投影仪")

    assert client.post(f"/admin/items/{item_id}/delete").status_code == 302
    second = client.post(f"/admin/items/{item_id}/delete")

    assert second.status_code == 404
    assert "RESOURCE_NOT_FOUND" in second.get_data(as_text=True)
    assert _item_id_of(app, "投影仪") is None


# ---------------------------------------------------------------- 真并发 20 轮 A


def test_concurrent_double_delete_exactly_one_wins(app):
    """同一物品被两个管理员会话同时删：恰好 1×302 + 1×404，无中间态。"""
    port, server_kwargs = start_threaded_server(app)
    cookie_admin = login_over_http(port, "A001")

    log_lines = [
        f"# Story 3.2 / 删除物品并发真实日志（双删）  生成于 {datetime.now():%Y-%m-%d %H:%M:%S}",
        "启动命令: python -m pytest tests/test_admin_delete.py -v -k concurrent",
        f"部署形态: 单进程 app.run(threaded=True, host={server_kwargs['host']},"
        f" port={server_kwargs['port']}, use_reloader=False)",
        "并发方式: threading.Barrier(2) + 2 线程 + 各自独立 TCP 连接（同一管理员会话）",
        "实验设定: 目标物品无在借、含 2 条已归还记录；两会话同时 POST /admin/items/<id>/delete",
        "-" * 72,
    ]
    try:
        for round_no in range(1, ROUNDS + 1):
            item_id = _direct_insert_item(f"并发删除目标 {round_no:02d}")
            _direct_insert_loan(item_id, user_pk=1, returned_at="2026-10-09 10:00:00")
            _direct_insert_loan(item_id, user_pk=2, returned_at="2026-10-09 10:00:00")

            results, spread_ms = race_request(
                port,
                [
                    ("first", cookie_admin, f"/admin/items/{item_id}/delete", {}),
                    ("second", cookie_admin, f"/admin/items/{item_id}/delete", {}),
                ],
            )
            statuses = sorted(status for status, _body in results.values())
            assert statuses == [302, 404], (round_no, statuses)
            assert _count("SELECT COUNT(*) FROM items WHERE id = ?", (item_id,)) == 0
            assert _count("SELECT COUNT(*) FROM loans WHERE item_id = ?", (item_id,)) == 0

            log_lines.append(
                f"round {round_no:02d}: first={results['first'][0]}"
                f" second={results['second'][0]}"
                f" | barrier 释放间隔={spread_ms:.2f}ms"
                f" | item=已删除 loans=0 OK"
            )
    finally:
        _write_log("concurrency-story32-double-delete-20-rounds.log", log_lines)


# ---------------------------------------------------------------- 真并发 20 轮 B


def test_concurrent_delete_versus_borrow_never_orphans_active_loan(app):
    """删除 vs 借阅对抗：串行化后只有两种结局，绝不出现「无物品却有在借」。"""
    port, server_kwargs = start_threaded_server(app)
    cookie_admin = login_over_http(port, "A001")
    cookie_student = login_over_http(port, "2024001")

    log_lines = [
        f"# Story 3.2 / 删除 vs 借阅并发真实日志  生成于 {datetime.now():%Y-%m-%d %H:%M:%S}",
        "启动命令: python -m pytest tests/test_admin_delete.py -v -k concurrent",
        f"部署形态: 单进程 app.run(threaded=True, host={server_kwargs['host']},"
        f" port={server_kwargs['port']}, use_reloader=False)",
        "并发方式: threading.Barrier(2) + 2 线程 + 各自独立 TCP 连接（管理员 / 学生各一）",
        "实验设定: 目标物品无在借、含 1 条已归还记录；同时 POST 删除 与 POST /borrow",
        "-" * 72,
    ]
    try:
        for round_no in range(1, ROUNDS + 1):
            _direct_execute("DELETE FROM loans")
            item_id = _direct_insert_item(f"删借对抗目标 {round_no:02d}")
            _direct_insert_loan(item_id, user_pk=2, returned_at="2026-10-09 10:00:00")

            results, spread_ms = race_request(
                port,
                [
                    ("delete", cookie_admin, f"/admin/items/{item_id}/delete", {}),
                    ("borrow", cookie_student, "/borrow", {"item_id": item_id}),
                ],
            )
            delete_status = results["delete"][0]
            borrow_status = results["borrow"][0]
            # 删除先赢 → borrow 撞 404；借阅先赢 → delete 撞 409。无第三种结局。
            assert (delete_status, borrow_status) in {(302, 404), (409, 302)}, (
                round_no,
                delete_status,
                borrow_status,
            )

            active = _count(
                "SELECT COUNT(*) FROM loans WHERE item_id = ? AND returned_at IS NULL",
                (item_id,),
            )
            item_exists = _count(
                "SELECT COUNT(*) FROM items WHERE id = ?", (item_id,)
            )
            if item_exists == 0:
                assert delete_status == 302 and borrow_status == 404
                assert active == 0
                assert _count(
                    "SELECT COUNT(*) FROM loans WHERE item_id = ?", (item_id,)
                ) == 0
            else:
                assert delete_status == 409 and borrow_status == 302
                assert active == 1
            log_lines.append(
                f"round {round_no:02d}: delete={delete_status} borrow={borrow_status}"
                f" | barrier 释放间隔={spread_ms:.2f}ms"
                f" | item_exists={item_exists} active={active} OK"
            )
    finally:
        _write_log("concurrency-story32-delete-vs-borrow-20-rounds.log", log_lines)


# ---------------------------------------------------------------- 真并发 20 轮 C


def test_concurrent_delete_of_in_borrow_item_both_409(app):
    """在借物品被两个会话同时删：两边都必须 409，物品与在借记录零变更。"""
    port, _server_kwargs = start_threaded_server(app)
    cookie_admin = login_over_http(port, "A001")

    for round_no in range(1, ROUNDS + 1):
        item_id = _direct_insert_item(f"在借拦截目标 {round_no:02d}")
        _direct_insert_loan(item_id, user_pk=2, returned_at=None)
        items_before = _items_snapshot(app)
        loans_before = _loans_snapshot(app)

        results, _spread = race_request(
            port,
            [
                ("first", cookie_admin, f"/admin/items/{item_id}/delete", {}),
                ("second", cookie_admin, f"/admin/items/{item_id}/delete", {}),
            ],
        )
        assert sorted(status for status, _body in results.values()) == [409, 409]
        for _status, body in results.values():
            assert "ITEM_IN_BORROW" in body
        assert _items_snapshot(app) == items_before
        assert _loans_snapshot(app) == loans_before
