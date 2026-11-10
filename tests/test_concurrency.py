"""Story 2.3：NFR-1.1 同一物品并发借阅——部分唯一索引的物理兜底。

铁律落实（对应 AC-2.3.1 ~ AC-2.3.10）：
- 真并发：真实部署形态 = 单进程 `app.run(threaded=True)` 起 HTTP 服务，
  两个线程各自持**独立 TCP 连接 + 独立会话 cookie**，在 `threading.Barrier`
  对齐后同时发起 `POST /borrow`——不是两次串行调用（AC-2.3.9）。
- D-021 白盒直测：测试用底层 sqlite3 直连**绕过服务层**插入重复在借记录，
  断言数据库抛出 IntegrityError（AC-2.3.4），与并发行为测试并列、不可替代。
- 断言精确：每轮 HTTP 状态集合恰好 {302, 409}、失败方错误码恰好
  ALREADY_BORROWED、未归还记录 COUNT 恰好 1，连跑 20 轮无例外（AC-2.3.1~2.3.3）。

本文件在 tests/ 内直接使用 sqlite3.connect 属白盒测试脚手架（PC-2 扫描
豁免 tests 目录，与 test_story_1_1_rules 同口径）；被测源码不含第二处连接。
"""

import http.client
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import pytest

import db as db_module
import services.loans as loans_service
from config import ERROR_MESSAGES, BizError
from concurrency_kit import (  # Story 2.3/2.4 共用同一份真并发脚手架
    client_borrow, client_login, direct_connect, direct_query,
    items_snapshot, item_row_state_text, login_over_http, race_post,
    seed_password, start_threaded_server,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = (
    REPO_ROOT
    / "_bmad-output"
    / "implementation-artifacts"
    / "concurrency-nfr11-20-rounds.log"
)
ROUNDS = 20
TARGET_ITEM_NAME = "投影仪"
STUDENT_A = "2024001"
STUDENT_B = "2024002"

# ------------------------------------------------ 薄包装（真并发走共享 race_post）

def race_borrow(port, cookie_a, cookie_b, item_id):
    """两个独立 TCP 连接在 barrier 对齐后同时 POST /borrow 抢借同一物品。"""
    return race_post(port, [("A", cookie_a, item_id), ("B", cookie_b, item_id)])


# ---------------------------------------------------------------- 真并发 20 轮


def test_ac_2_3_1_to_2_3_3_8_9_concurrent_borrow_20_rounds(app):
    """AC-2.3.1/2/3/8/9：真实 threaded 服务器上 20 轮双连接抢借同一物品。"""
    target = direct_query(
        "SELECT id FROM items WHERE name = ?", (TARGET_ITEM_NAME,))[0]["id"]
    items_before = items_snapshot()
    loans_total_before = direct_query("SELECT COUNT(*) AS c FROM loans")[0]["c"]
    assert loans_total_before == 0

    port, server_kwargs = start_threaded_server(app)
    cookie_a = login_over_http(port, STUDENT_A)
    cookie_b = login_over_http(port, STUDENT_B)

    log_lines = [
        f"# Story 2.3 / NFR-1.1 并发借阅真实日志  生成于 {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"启动命令: python -m pytest tests/test_concurrency.py -v -k 20_rounds",
        f"部署形态: 单进程 app.run(threaded=True, host={server_kwargs['host']},"
        f" port={server_kwargs['port']}, use_reloader=False)",
        "并发方式: threading.Barrier(2) + 2 线程 + 各自独立 TCP 连接与会话 cookie",
        f"抢借物品: {TARGET_ITEM_NAME} (id={target}), 参与者: {STUDENT_A} vs {STUDENT_B}",
        "-" * 72,
    ]
    success_count = 0
    try:
        for round_no in range(1, ROUNDS + 1):
            results, spread_ms = race_borrow(port, cookie_a, cookie_b, target)
            codes = sorted(status for status, _body in results.values())
            # AC-2.3.1：状态集合恰好 {302, 409}，无一例外
            assert codes == [302, 409], f"第{round_no}轮状态集合={codes}"
            loser = min(results, key=lambda name: results[name][0] == 302)
            _status, loser_body = results[loser]
            # AC-2.3.1 And：失败方错误码恰好 ALREADY_BORROWED（文案与错误码同源）
            assert "ALREADY_BORROWED" in loser_body, f"第{round_no}轮失败方缺错误码"
            assert ERROR_MESSAGES["ALREADY_BORROWED"] in loser_body
            # AC-2.3.2 / AC-2.3.3：未归还记录恰好 1，绝不出现 2 或 0
            active = direct_query(
                "SELECT COUNT(*) AS c FROM loans"
                " WHERE item_id = ? AND returned_at IS NULL", (target,))[0]["c"]
            assert active == 1, f"第{round_no}轮未归还记录={active}"
            success_count += 1

            holder = direct_query(
                "SELECT id, user_id FROM loans"
                " WHERE item_id = ? AND returned_at IS NULL", (target,))[0]
            # 轮间重置：把本轮胜者记录标记归还（保留行，供 AC-2.3.8 计数）
            direct_query(
                "UPDATE loans SET returned_at = ? WHERE id = ?",
                (db_module.now_text(), holder["id"]))

            log_lines.append(
                f"round {round_no:02d}: A({STUDENT_A})={results['A'][0]}"
                f" B({STUDENT_B})={results['B'][0]}"
                f" | barrier 释放间隔={spread_ms:.2f}ms"
                f" | 胜方=user_id {holder['user_id']} (loan_id={holder['id']})"
                f" | active_count=1 OK")
    finally:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    # AC-2.3.8：失败无副作用——loans 总行数 = 成功数；items 与快照逐字段一致
    assert success_count == ROUNDS
    loans_total_after = direct_query("SELECT COUNT(*) AS c FROM loans")[0]["c"]
    assert loans_total_after == loans_total_before + ROUNDS
    assert items_snapshot() == items_before


# ---------------------------------------------------------------- D-021 白盒直测


def test_ac_2_3_4_bypass_service_duplicate_insert_raises_integrity_error(app):
    """AC-2.3.4（D-021）：底层直连绕过服务层，重复在借插入被物理拒绝。"""
    target = direct_query("SELECT id FROM items ORDER BY id LIMIT 1")[0]["id"]
    users = direct_query("SELECT id FROM users ORDER BY id LIMIT 2")
    conn = direct_connect()
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO loans (item_id, user_id, borrowed_at, due_at)"
            " VALUES (?, ?, ?, ?)",
            (target, users[0]["id"],
             "2026-11-10 09:00:00", "2026-11-17 09:00:00"))
        with pytest.raises(sqlite3.IntegrityError) as excinfo:
            conn.execute(
                "INSERT INTO loans (item_id, user_id, borrowed_at, due_at)"
                " VALUES (?, ?, ?, ?)",
                (target, users[1]["id"],
                 "2026-11-10 09:01:00", "2026-11-17 09:01:00"))
        assert "UNIQUE constraint failed: loans.item_id" in str(excinfo.value)
        # 插入失败后该 item_id 的未归还记录仍恰好 1 条
        count = conn.execute(
            "SELECT COUNT(*) FROM loans WHERE item_id = ? AND returned_at IS NULL",
            (target,)).fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def test_ac_2_3_5_partial_unique_index_shape(app):
    """AC-2.3.5：PRAGMA 证明 ux_loans_active_item 是 partial=1 的单列唯一索引。"""
    conn = direct_connect()
    try:
        cursor = conn.execute("PRAGMA index_list('loans')")
        columns = [meta[0] for meta in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        match = [r for r in rows if r["name"] == "ux_loans_active_item"]
        assert len(match) == 1
        assert match[0]["unique"] == 1
        assert match[0]["partial"] == 1
        info = conn.execute("PRAGMA index_info('ux_loans_active_item')").fetchall()
        # index_info 列序为 seqno | cid | name，索引列名取第 3 列
        assert [row[2] for row in info] == ["item_id"]
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index'"
            " AND name='ux_loans_active_item'").fetchone()[0]
        assert "WHERE returned_at IS NULL" in sql
    finally:
        conn.close()


# ---------------------------------------------------------------- 行为补充


def test_ac_2_3_6_returned_item_reborrowable_by_other(app):
    """AC-2.3.6：唯一在借记录归还后，另一人借同一物品成功（302）。"""
    target = direct_query(
        "SELECT id FROM items WHERE name = ?", (TARGET_ITEM_NAME,))[0]["id"]

    first = app.test_client()
    client_login(first, STUDENT_A)
    assert client_borrow(first, target).status_code == 302
    loan = direct_query(
        "SELECT id FROM loans WHERE item_id = ? AND returned_at IS NULL",
        (target,))[0]
    assert first.post(f"/return/{loan['id']}").status_code == 302

    second = app.test_client()
    client_login(second, STUDENT_B)
    assert client_borrow(second, target).status_code == 302
    holder = direct_query(
        "SELECT u.student_id FROM loans l JOIN users u ON u.id = l.user_id"
        " WHERE l.item_id = ? AND l.returned_at IS NULL", (target,))
    assert [row["student_id"] for row in holder] == [STUDENT_B]


def test_ac_2_3_7_no_intermediate_state(app):
    """AC-2.3.7（NFR-1.4）：列表「在借/可借」与未归还 COUNT 始终一致。"""
    target = direct_query(
        "SELECT id FROM items WHERE name = ?", (TARGET_ITEM_NAME,))[0]["id"]
    client = app.test_client()

    def active_count():
        return direct_query(
            "SELECT COUNT(*) AS c FROM loans"
            " WHERE item_id = ? AND returned_at IS NULL", (target,))[0]["c"]

    # 借阅前：无记录 → 可借
    assert active_count() == 0
    assert item_row_state_text(client, TARGET_ITEM_NAME) == "可借"

    client_login(client, STUDENT_A)
    assert client_borrow(client, target).status_code == 302
    assert active_count() == 1
    assert item_row_state_text(client, TARGET_ITEM_NAME) == "在借"

    loan = direct_query(
        "SELECT id FROM loans WHERE item_id = ? AND returned_at IS NULL",
        (target,))[0]
    assert client.post(f"/return/{loan['id']}").status_code == 302
    assert active_count() == 0
    assert item_row_state_text(client, TARGET_ITEM_NAME) == "可借"


# ---------------------------------------------------------------- AC-2.3.10


class _ForeignKeyBoomConnection:
    """把 INSERT loans 注入成外键失败的 IntegrityError（非唯一约束）。"""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, parameters=()):
        if "INSERT INTO loans" in sql:
            raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")
        return self._conn.execute(sql, parameters)


def test_ac_2_3_10_non_unique_integrity_error_is_not_biz_error(app, monkeypatch):
    """AC-2.3.10：非唯一约束 IntegrityError 不映射为 409，原样上抛。"""
    real_get_db = db_module.get_db
    monkeypatch.setattr(
        loans_service, "get_db",
        lambda: _ForeignKeyBoomConnection(real_get_db()))
    with app.app_context():
        with pytest.raises(sqlite3.IntegrityError) as excinfo:
            loans_service.borrow_item(1, 1)
    # 抛出的是原始 IntegrityError，而不是被伪装的 409 业务冲突
    assert not isinstance(excinfo.value, BizError)
    assert "FOREIGN KEY constraint failed" in str(excinfo.value)


def test_ac_2_3_10_http_presents_500_not_409(app, monkeypatch):
    """AC-2.3.10 出口侧：注入外键错误后，真实 threaded 服务器返回 500 而非 409。"""
    real_get_db = db_module.get_db
    monkeypatch.setattr(
        loans_service, "get_db",
        lambda: _ForeignKeyBoomConnection(real_get_db()))
    port, _server_kwargs = start_threaded_server(app)
    cookie = login_over_http(port, STUDENT_A)
    target = direct_query("SELECT id FROM items ORDER BY id LIMIT 1")[0]["id"]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    conn.request(
        "POST", "/borrow", body=urlencode({"item_id": str(target)}),
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Cookie": cookie})
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    assert resp.status == 500, f"应为 500，实际 {resp.status}"
    assert "ALREADY_BORROWED" not in body
    assert ERROR_MESSAGES["ALREADY_BORROWED"] not in body
