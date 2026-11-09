"""Story 2.1：借阅物品——六步判定与应还日期（AC-2.1.1 ~ AC-2.1.12）。"""

import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import db as db_module
import services.loans as loans_service
from config import BORROW_DAYS, ERROR_MESSAGES, TIME_FORMAT, BizError

REPO_ROOT = Path(__file__).resolve().parents[1]


def seed_password(student_id):
    """从 db.SEED_USERS 取种子口令；测试文件不写死明文凭据。"""
    for sid, _name, _role, password in db_module.SEED_USERS:
        if sid == student_id:
            return password
    raise AssertionError(f"非种子账号: {student_id}")


def login(client, student_id):
    response = client.post(
        "/login", data={"student_id": student_id, "password": seed_password(student_id)}
    )
    assert response.status_code == 302


def seed_active_loan(app, item_id, user_id, borrowed_at, due_at):
    """预置一条未归还记录（returned_at 写入 SQL 字面量 NULL）。"""
    with app.app_context():
        db_module.get_db().execute(
            "INSERT INTO loans (item_id, user_id, borrowed_at, due_at, returned_at)"
            " VALUES (?, ?, ?, ?, NULL)",
            (item_id, user_id, borrowed_at, due_at),
        )


def borrow(client, item_id):
    return client.post("/borrow", data={"item_id": str(item_id)})


def active_loans(app, user_id=None):
    with app.app_context():
        db = db_module.get_db()
        if user_id is None:
            return db.execute(
                "SELECT COUNT(*) AS c FROM loans WHERE returned_at IS NULL"
            ).fetchone()["c"]
        return db.execute(
            "SELECT COUNT(*) AS c FROM loans"
            " WHERE returned_at IS NULL AND user_id = ?",
            (user_id,),
        ).fetchone()["c"]


def snapshot_db(app):
    with app.app_context():
        db = db_module.get_db()
        loans_rows = [tuple(r) for r in db.execute("SELECT * FROM loans ORDER BY id")]
        items_rows = [tuple(r) for r in db.execute("SELECT * FROM items ORDER BY id")]
    return loans_rows, items_rows


# ---------------------------------------------------------------- 正常路径


def test_ac_2_1_1_borrow_success_redirects_with_due_date(client, app):
    """AC-2.1.1：借阅成功 302 回列表，loans 恰好 +1，due_at = borrowed_at + 7 天。"""
    login(client, "2024001")
    response = borrow(client, 1)
    assert response.status_code == 302
    assert response.headers["Location"] == "/items"

    body = client.get("/items").get_data(as_text=True)
    assert "借阅成功，应还日期" in body

    with app.app_context():
        row = db_module.get_db().execute(
            "SELECT * FROM loans WHERE item_id = 1 AND returned_at IS NULL"
        ).fetchone()
    assert row is not None
    assert row["user_id"] == 1
    borrowed_at = datetime.strptime(row["borrowed_at"], TIME_FORMAT)
    due_at = datetime.strptime(row["due_at"], TIME_FORMAT)
    assert due_at - borrowed_at == timedelta(days=BORROW_DAYS)
    # 按天为整数，时分秒不漂移
    assert borrowed_at.time() == due_at.time()
    assert active_loans(app) == 1


def test_ac_2_1_2_list_shows_borrowed_immediately(client, app):
    """AC-2.1.2：借阅成功后立即 GET /items，该物品「在借」并显示应还日期。"""
    login(client, "2024001")
    borrow(client, 1)
    response = client.get("/items")
    assert response.status_code == 200
    assert response.headers.get("Cache-Control") == "no-store"
    html = response.get_data(as_text=True)
    assert "在借" in html
    with app.app_context():
        due_at = db_module.get_db().execute(
            "SELECT due_at FROM loans WHERE item_id = 1"
        ).fetchone()["due_at"]
    assert due_at[:10] in html  # 列表展示的应还日期与库内一致


# ---------------------------------------------------------------- 失败判定


def test_ac_2_1_3_item_taken_by_other(client, app):
    """AC-2.1.3：物品被他人借走 → 409 ALREADY_BORROWED，行数不变，列表即时更新。"""
    seed_active_loan(app, 1, 2, "2026-11-08 09:00:00", "2026-11-15 09:00:00")
    login(client, "2024001")
    response = borrow(client, 1)
    assert response.status_code == 409
    body = response.get_data(as_text=True)
    assert "ALREADY_BORROWED" in body
    assert ERROR_MESSAGES["ALREADY_BORROWED"] in body
    assert active_loans(app) == 1  # 只有他人那条

    items_page = client.get("/items").get_data(as_text=True)
    assert "在借" in items_page


def test_ac_2_1_4_unknown_item_is_404(client, app):
    """AC-2.1.4：item_id 不存在 → 404 RESOURCE_NOT_FOUND（D-011 语义合并）。"""
    login(client, "2024001")
    response = borrow(client, 99999)
    assert response.status_code == 404
    assert "RESOURCE_NOT_FOUND" in response.get_data(as_text=True)
    assert active_loans(app) == 0


def test_ac_2_1_5_unavailable_item_blocked(client, app):
    """AC-2.1.5：停用物品 → 409 ITEM_UNAVAILABLE，不产生记录。"""
    with app.app_context():
        db_module.get_db().execute(
            "UPDATE items SET status = 'unavailable' WHERE id = 1"
        )
    login(client, "2024001")
    response = borrow(client, 1)
    assert response.status_code == 409
    assert "ITEM_UNAVAILABLE" in response.get_data(as_text=True)
    assert active_loans(app) == 0


def test_ac_2_1_6_double_borrow_paths_identical(client, app):
    """AC-2.1.6：双击的第二次（④路径）与唯一索引兜底（⑥路径）响应逐字一致。"""
    login(client, "2024001")
    first = borrow(client, 1)
    assert first.status_code == 302
    second = borrow(client, 1)  # ④：本人已持有
    assert second.status_code == 409

    # ⑥：绕过 ④⑤ 直接撞索引（模拟并发竞态），异常映射与 ④ 完全一致
    with app.app_context():
        real_counts = loans_service._loan_counts
        loans_service._loan_counts = lambda conn, item_id, user_id: {
            "user_active": 0,
            "item_active": 0,
        }
        try:
            with pytest.raises(BizError) as excinfo:
                loans_service.borrow_item(1, 1)
        finally:
            loans_service._loan_counts = real_counts
    err = excinfo.value
    assert (err.status_code, err.error_code) == (409, "ALREADY_BORROWED")
    assert err.message == ERROR_MESSAGES["ALREADY_BORROWED"]
    assert "ALREADY_BORROWED" in second.get_data(as_text=True)
    assert ERROR_MESSAGES["ALREADY_BORROWED"] in second.get_data(as_text=True)
    # 两条路径都不新增记录（⑥ 触发前已 INSERT 的那条被回滚）
    assert active_loans(app) == 1


def test_ac_2_1_7_quota_of_three(client, app):
    """AC-2.1.7：在借 3 件再借 → 409 LIMIT_EXCEEDED，行数与 items.status 不变。"""
    login(client, "2024001")
    for item_id in (1, 2, 3):
        assert borrow(client, item_id).status_code == 302
    before = snapshot_db(app)
    response = borrow(client, 4)
    assert response.status_code == 409
    assert ERROR_MESSAGES["LIMIT_EXCEEDED"] in response.get_data(as_text=True)
    assert snapshot_db(app) == before


# ---------------------------------------------------------- 六步顺序优先级


def test_ac_2_1_8_priority_matrix_four_combinations(client, app):
    """AC-2.1.8：同时命中多条判定时，严格按六步顺序取序号最小者。"""
    # 组合 1：未登录 + item_id 不存在 → ① 302 → /login?next=
    response = client.post("/borrow", data={"item_id": "99999"})
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login?next=")

    login(client, "2024001")
    # 组合 2：item_id 不存在 + 已满额 → ② 404（而非 ⑤ 409）
    for item_id in (1, 2, 3):
        assert borrow(client, item_id).status_code == 302
    response = borrow(client, 99999)
    assert response.status_code == 404
    assert "RESOURCE_NOT_FOUND" in response.get_data(as_text=True)

    # 组合 3：物品停用 + 已满额 → ③ 409 ITEM_UNAVAILABLE（早于 ⑤）
    with app.app_context():
        db_module.get_db().execute(
            "UPDATE items SET status = 'unavailable' WHERE id = 4"
        )
    response = borrow(client, 4)
    assert response.status_code == 409
    assert "ITEM_UNAVAILABLE" in response.get_data(as_text=True)

    # 组合 4：本人已持有 + 已满额 → ④ 409 ALREADY_BORROWED（早于 ⑤）
    response = borrow(client, 1)
    assert response.status_code == 409
    assert "ALREADY_BORROWED" in response.get_data(as_text=True)


# ---------------------------------------------------------- 实现结构约束


class _CountingConnection:
    """记录执行过的 SQL，用于 AC-2.1.9 的查询次数断言。"""

    def __init__(self, conn):
        self._conn = conn
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append(sql)
        return self._conn.execute(sql, params)


def test_ac_2_1_9_single_queries_per_borrow(client, app, monkeypatch):
    """AC-2.1.9：对 items 恰一条 SELECT；④⑤ 一条聚合查询（loans 读取 1 次）。"""
    login(client, "2024001")
    recorded = _CountingConnection(None)

    def counting_get_db():
        recorded._conn = db_module.get_db()
        return recorded

    monkeypatch.setattr(loans_service, "get_db", counting_get_db)
    with app.app_context():
        due_at = loans_service.borrow_item(1, 1)
    assert due_at

    selects_on_items = [s for s in recorded.executed if re.search(r"FROM items", s)]
    selects_on_loans = [s for s in recorded.executed if re.search(r"FROM loans", s)]
    inserts = [s for s in recorded.executed if s.strip().upper().startswith("INSERT")]
    assert len(selects_on_items) == 1  # ②③ 同一行
    assert len(selects_on_loans) == 1  # ④⑤ 同一条聚合
    assert len(inserts) == 1


def test_ac_2_1_10_begin_immediate_only(client, app):
    """AC-2.1.10：写事务用 BEGIN IMMEDIATE；全项目 BEGIN DEFERRED 0 命中。"""
    db_source = (REPO_ROOT / "db.py").read_text(encoding="utf-8")
    loans_source = (REPO_ROOT / "services" / "loans.py").read_text(encoding="utf-8")
    assert "BEGIN IMMEDIATE" in db_source
    # COUNT（_loan_counts 调用）与 INSERT 都落在 write_transaction() 块内
    with_block = loans_source.index("with write_transaction():")
    assert with_block < loans_source.rindex("_loan_counts(conn, item_id, user_id)")
    assert with_block < loans_source.index("INSERT INTO loans")

    deferred = "BEGIN " "DEFERRED"
    skip_dirs = {".git", "node_modules", "__pycache__", "_bmad", "testtmp", ".claude", "tests"}
    for path in REPO_ROOT.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT)
        if any(part in skip_dirs for part in rel.parts):
            continue
        assert deferred not in path.read_text(encoding="utf-8"), f"{rel} 出现 BEGIN DEFERRED"


def test_ac_2_1_11_failures_leave_no_trace(client, app):
    """AC-2.1.11：每种失败请求前后，loans 行数与 items 全字段逐字段一致。"""
    login(client, "2024001")
    with app.app_context():
        db_module.get_db().execute(
            "UPDATE items SET status = 'unavailable' WHERE id = 5"
        )
    seed_active_loan(app, 6, 2, "2026-11-08 09:00:00", "2026-11-15 09:00:00")

    # 阶段 A：404 / 409 停用 / 409 已被他人借走
    baseline = snapshot_db(app)
    for item_id, expected in ((99999, 404), (5, 409), (6, 409)):
        assert borrow(client, item_id).status_code == expected
    assert snapshot_db(app) == baseline

    # 阶段 B：占满额度后，限额拦截失败同样零副作用
    for item_id in (1, 2, 3):
        assert borrow(client, item_id).status_code == 302
    baseline = snapshot_db(app)
    assert borrow(client, 4).status_code == 409  # LIMIT_EXCEEDED
    assert borrow(client, 99999).status_code == 404
    assert snapshot_db(app) == baseline


# ---------------------------------------------------------- 逾期计入额度


def test_ac_2_1_12_overdue_counts_toward_quota(client, app):
    """AC-2.1.12：逾期计入额度；逾期本身不构成拦截。"""
    past = (datetime.now() - timedelta(days=3)).strftime(TIME_FORMAT)
    seed_active_loan(app, 1, 1, past, past)  # 逾期记录
    login(client, "2024001")
    assert borrow(client, 2).status_code == 302
    assert borrow(client, 3).status_code == 302
    # 1 逾期 + 2 正常 = 3 件 → 第 4 件被 ⑤ 拦截
    response = borrow(client, 4)
    assert response.status_code == 409
    assert "LIMIT_EXCEEDED" in response.get_data(as_text=True)


def test_ac_2_1_12_overdue_alone_does_not_block(client, app):
    """AC-2.1.12 后半段：1 条逾期 + 1 条正常（合计 2 件）可再借第 3 件。"""
    past = (datetime.now() - timedelta(days=3)).strftime(TIME_FORMAT)
    seed_active_loan(app, 1, 1, past, past)
    login(client, "2024001")
    assert borrow(client, 2).status_code == 302
    response = borrow(client, 3)
    assert response.status_code == 302


def test_non_numeric_item_id_is_400(client, app):
    """路由层入参校验：非数字 item_id → 400 INVALID_INPUT（PC-9）。"""
    login(client, "2024001")
    response = client.post("/borrow", data={"item_id": "abc"})
    assert response.status_code == 400
    assert "INVALID_INPUT" in response.get_data(as_text=True)
    assert active_loans(app) == 0


def test_borrow_concurrency_smoke(app):
    """并发冒烟（规格承诺项）：两会话同抢一件物品，恰一成功一冲突，20 轮。

    正式的 NFR-1.1 白盒验收属 Story 2.3，本用例仅验证事务与唯一索引机制可用。
    登录先在主线程完成（辅助函数断言 302），线程内只做 barrier + 并发 POST。
    """
    import threading

    for round_no in range(1, 21):
        with app.app_context():
            db_module.get_db().execute("DELETE FROM loans")
        clients = {}
        for tag, sid in (("a", "2024001"), ("b", "2024002")):
            own_client = app.test_client()
            login(own_client, sid)
            clients[tag] = own_client

        barrier = threading.Barrier(2)
        results = {}
        thread_errors = {}

        def attempt(tag):
            try:
                barrier.wait()
                response = clients[tag].post("/borrow", data={"item_id": "1"})
                results[tag] = (response.status_code, response.headers.get("Location", ""))
            except BaseException as exc:
                thread_errors[tag] = repr(exc)

        threads = [threading.Thread(target=attempt, args=(tag,)) for tag in ("a", "b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert thread_errors == {}, (round_no, thread_errors)
        codes = sorted(code for code, _ in results.values())
        assert codes == [302, 409], (round_no, results)
        with app.app_context():
            active = db_module.get_db().execute(
                "SELECT COUNT(*) AS c FROM loans WHERE returned_at IS NULL"
            ).fetchone()["c"]
        assert active == 1, (round_no, results, active)
