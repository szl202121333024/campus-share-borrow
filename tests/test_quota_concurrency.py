"""Story 2.4：NFR-1.2 同一用户并发超额 —— BEGIN IMMEDIATE 的事务原子性。

严格复用 Story 2.3 的共享脚手架（concurrency_kit）：单进程 threaded 服务器、
独立 TCP 连接、threading.Barrier 对齐后同时发起——不是任何串行调用。

- AC-2.4.1 ~ 2.4.3：20 轮真并发主实验（同一用户差 1 件满额，两线程同时
  借**不同**物品），断言恰好 {302, 409}、409 方恰 LIMIT_EXCEEDED、
  未归还 COUNT 恰好 3，20 轮无一例外；逐轮真实日志入库（SM-2 同机制）。
- AC-2.4.4：D-021 白盒直测在本故事测试集**独立执行、独立计数**
  （epics 原文：合并执行即视为 NFR-1.1 与 NFR-1.2 被合并）。
- AC-2.4.5：反向证明——绕过服务层给同一用户直插第 4 条不同物品的
  未归还记录，数据库**照单全收**，证明额度没有任何 DB 级兜底。
- AC-2.4.6 / 2.4.7 / 2.4.10：源码结构扫描（校验先于插入、额度聚合唯一、
  限额逻辑无 role 分支）。

本文件在 tests/ 内直接使用 sqlite3 属白盒测试脚手架（PC-2 扫描豁免
tests 目录，与 test_story_1_1_rules、test_concurrency 同口径）。
"""

import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

import db as db_module
from config import ERROR_MESSAGES
from concurrency_kit import (
    client_login,
    direct_connect,
    direct_query,
    login_over_http,
    race_post,
    start_threaded_server,
    write_evidence_log,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ROUNDS = 20
STUDENT_A = "2024001"
STUDENT_B = "2024002"
ADMIN_SID = "A001"
# 主实验固定用物：物品 1、2 = 预置在借；物品 3、4 = 两个并发请求的目标
HELD_ITEMS = (1, 2)
RACE_ITEMS = (3, 4)

SOURCE_SCAN_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", "_bmad", "testtmp", ".claude", "tests",
}


def business_py_files():
    for path in REPO_ROOT.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT)
        if any(part in SOURCE_SCAN_SKIP_DIRS for part in rel.parts):
            continue
        yield rel.as_posix(), path.read_text(encoding="utf-8")


def user_pk(student_id):
    return direct_query(
        "SELECT id FROM users WHERE student_id = ?", (student_id,))[0]["id"]


def seed_active_loan(user_id, item_id):
    """测试预置：绕过服务层直接构造一条未归还借阅。"""
    borrowed = db_module.now_text()
    direct_query(
        "INSERT INTO loans (item_id, user_id, borrowed_at, due_at)"
        " VALUES (?, ?, ?, ?)",
        (item_id, user_id, borrowed, db_module.due_text(borrowed)))


def active_count(user_id):
    """AC-2.4.2 的原文查询：未归还记录数。"""
    return direct_query(
        "SELECT COUNT(*) AS c FROM loans"
        " WHERE user_id = ? AND returned_at IS NULL", (user_id,))[0]["c"]


# ---------------------------------------------------- AC-2.4.1 ~ 2.4.3 主实验


def test_ac_2_4_1_to_2_4_3_concurrent_quota_20_rounds(app):
    """差 1 件满额的用户，两线程同时借两件**不同**物品：恰好一 302 一 409。"""
    u = user_pk(STUDENT_A)
    port, server_kwargs = start_threaded_server(app)
    # 同一用户的会话 cookie 在两个独立 TCP 连接上并发使用
    cookie = login_over_http(port, STUDENT_A)

    log_lines = [
        f"# Story 2.4 / NFR-1.2 并发超额真实日志  生成于"
        f" {datetime.now():%Y-%m-%d %H:%M:%S}",
        "启动命令: python -m pytest tests/test_quota_concurrency.py -v -k 20_rounds",
        f"部署形态: 单进程 app.run(threaded=True, host={server_kwargs['host']},"
        f" port={server_kwargs['port']}, use_reloader=False)",
        "并发方式: threading.Barrier(2) + 2 线程 + 各自独立 TCP 连接（同一用户会话）",
        f"实验设定: {STUDENT_A} 在借 {HELD_ITEMS}（差1件满额），并发借"
        f" {RACE_ITEMS[0]} 与 {RACE_ITEMS[1]}",
        "-" * 72,
    ]
    ok_rounds = 0
    try:
        for round_no in range(1, ROUNDS + 1):
            direct_query("DELETE FROM loans")
            for held in HELD_ITEMS:
                seed_active_loan(u, held)
            assert active_count(u) == 2, f"第{round_no}轮预置失败"

            results, spread_ms = race_post(port, [
                ("item3", cookie, RACE_ITEMS[0]),
                ("item4", cookie, RACE_ITEMS[1]),
            ])
            codes = sorted(status for status, _body in results.values())
            # AC-2.4.1：恰好 1 个 302、1 个 409（含错误码断言），20 轮无一例外
            assert codes == [302, 409], f"第{round_no}轮状态集合={codes}"
            loser = min(results, key=lambda n: results[n][0] == 302)
            loser_body = results[loser][1]
            assert "LIMIT_EXCEEDED" in loser_body, f"第{round_no}轮失败方缺错误码"
            assert ERROR_MESSAGES["LIMIT_EXCEEDED"] in loser_body

            # AC-2.4.2：未归还 COUNT 恰好 3，不得为 4
            final_count = active_count(u)
            assert final_count == 3, f"第{round_no}轮在借数={final_count}（应为3）"

            winner = max(results, key=lambda n: results[n][0] == 302)
            ok_rounds += 1
            log_lines.append(
                f"round {round_no:02d}: item3={results['item3'][0]}"
                f" item4={results['item4'][0]}"
                f" | barrier 释放间隔={spread_ms:.2f}ms"
                f" | 成功方=物品 {winner[-1]}"
                f" | 失败方={loser} LIMIT_EXCEEDED"
                f" | user_active={final_count} OK")
    finally:
        write_evidence_log("concurrency-nfr12-20-rounds.log", log_lines)

    assert ok_rounds == ROUNDS, "AC-2.4.3：20 轮必须全部满足 AC-2.4.1/2.4.2"
    # 20 轮中出现过 4 的记录数一差不可能：上面每轮已逐轮断言 ==3，
    # 这里再防一手日志完整性（逐轮行数 = 轮数）
    assert len([line for line in log_lines if line.startswith("round ")]) == ROUNDS


# -------------------------------------------------- AC-2.4.4 白盒直测（独立执行）


def test_ac_2_4_4_item_unique_index_white_box_replayed_independently(app):
    """AC-2.4.4（D-021）：与 AC-2.3.4 同法，但在本故事测试集独立执行与计数。"""
    target = direct_query("SELECT id FROM items ORDER BY id LIMIT 1")[0]["id"]
    users = direct_query("SELECT id FROM users ORDER BY id LIMIT 2")
    conn = direct_connect()
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        borrowed = db_module.now_text()
        conn.execute(
            "INSERT INTO loans (item_id, user_id, borrowed_at, due_at)"
            " VALUES (?, ?, ?, ?)",
            (target, users[0]["id"], borrowed, db_module.due_text(borrowed)))
        with pytest.raises(sqlite3.IntegrityError) as excinfo:
            conn.execute(
                "INSERT INTO loans (item_id, user_id, borrowed_at, due_at)"
                " VALUES (?, ?, ?, ?)",
                (target, users[1]["id"], borrowed, db_module.due_text(borrowed)))
        assert "UNIQUE constraint failed: loans.item_id" in str(excinfo.value)
    finally:
        conn.close()


# -------------------------------------------------------- AC-2.4.5 反向证明


def test_ac_2_4_5_quota_has_no_database_backstop(app):
    """AC-2.4.5：同用户第 4 条（不同物品）直插被数据库**接受**。

    这正是额度必须靠 BEGIN IMMEDIATE 原子性、且必须真并发测试的理由：
    物品维度有唯一索引物理兜底（AC-2.4.4），用户额度没有任何数据库级兜底。
    """
    u = user_pk(STUDENT_A)
    conn = direct_connect()
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        borrowed = db_module.now_text()
        due = db_module.due_text(borrowed)
        for item_id in (1, 2, 3):
            conn.execute(
                "INSERT INTO loans (item_id, user_id, borrowed_at, due_at)"
                " VALUES (?, ?, ?, ?)", (item_id, u, borrowed, due))
        # 第 4 条同用户、不同物品——不得抛任何约束异常
        conn.execute(
            "INSERT INTO loans (item_id, user_id, borrowed_at, due_at)"
            " VALUES (?, ?, ?, ?)", (4, u, borrowed, due))
        count = conn.execute(
            "SELECT COUNT(*) FROM loans WHERE user_id = ? AND returned_at IS NULL",
            (u,)).fetchone()[0]
        assert count == 4, "直插应被接受——数据库不拦越限，才是本用例的证明目的"
    finally:
        conn.close()

    # 并且证明：loans 上任何唯一索引都只建在物品维度，不存在 user_id 唯一索引
    conn2 = direct_connect()
    try:
        for _seq, name, unique, _origin, _partial in conn2.execute(
                "PRAGMA index_list('loans')").fetchall():
            if unique:
                cols = [row[2] for row in conn2.execute(
                    f"PRAGMA index_info('{name}')").fetchall()]
                assert cols == ["item_id"], f"{name} 不应是 user_id 维度的唯一索引"
    finally:
        conn2.close()


# -------------------------------------------------------- AC-2.4.6 事务结构


def test_ac_2_4_6_begin_immediate_structure():
    """AC-2.4.6：校验（额度）先于 INSERT 且同在 BEGIN IMMEDIATE 事务内。"""
    db_source = (REPO_ROOT / "db.py").read_text(encoding="utf-8")
    loans_source = (REPO_ROOT / "services" / "loans.py").read_text(encoding="utf-8")

    assert "BEGIN IMMEDIATE" in db_source
    # 连接必须是显式自动提交（isolation_level=None），不得停留在 Python 默认隐式事务
    assert "isolation_level=None" in db_source

    with_block = loans_source.index("with write_transaction():")
    quota_call = loans_source.rindex("get_remaining_quota(user_id)")
    insert_at = loans_source.index("INSERT INTO loans")
    assert with_block < quota_call < insert_at, "额度校验必须先于插入、同处一个写事务"

    deferred = "BEGIN " "DEFERRED"
    for rel, text in business_py_files():
        assert deferred not in text, f"{rel} 出现 BEGIN DEFERRED"


# ------------------------------------------------------ AC-2.4.7 额度 SQL 唯一


def test_ac_2_4_7_quota_aggregate_has_single_source():
    """AC-2.4.7：额度计数 SQL 全项目只有一处，位于 get_remaining_quota 函数体内。"""
    hits = []
    for rel, text in business_py_files():
        for i, line in enumerate(text.splitlines(), start=1):
            if "COUNT(*)" in line and "FROM loans" in line:
                hits.append((rel, i))
    assert len(hits) == 1, f"额度聚合计数应恰好 1 处，实际 {hits}"
    rel, hit_line = hits[0]
    assert rel == "services/loans.py"

    lines = (REPO_ROOT / "services" / "loans.py").read_text(
        encoding="utf-8").splitlines()
    def_start = next(i for i, l in enumerate(lines, start=1)
                     if l.startswith("def get_remaining_quota"))
    def_end = next(i for i, l in enumerate(lines, start=def_start + 1)
                   if l.startswith("def "))
    assert def_start <= hit_line < def_end, "唯一的额度聚合必须在 get_remaining_quota 内"

    # 借阅前置校验与页面指示都调用该函数，不存在第二份额度实现
    loans_source = "\n".join(lines)
    assert "get_remaining_quota(user_id)" in loans_source
    assert loans_source.count("COUNT(*) AS active_count") == 1


# ------------------------------------------------------ AC-2.4.8 不误拒


def test_ac_2_4_8_two_users_concurrent_no_false_reject(app):
    """AC-2.4.8：U 在借 2、V 在借 0，并发各借一件 → 两个都必须 302。"""
    u_a = user_pk(STUDENT_A)
    u_b = user_pk(STUDENT_B)
    port, _server_kwargs = start_threaded_server(app)
    cookie_a = login_over_http(port, STUDENT_A)
    cookie_b = login_over_http(port, STUDENT_B)

    rounds = 10
    for round_no in range(1, rounds + 1):
        direct_query("DELETE FROM loans")
        for held in HELD_ITEMS:
            seed_active_loan(u_a, held)
        results, _spread = race_post(port, [
            ("A", cookie_a, RACE_ITEMS[0]),
            ("B", cookie_b, RACE_ITEMS[1]),
        ])
        codes = [results["A"][0], results["B"][0]]
        assert codes == [302, 302], f"第{round_no}轮出现误拒：{codes}"
    assert active_count(u_a) == 3
    assert active_count(u_b) == 1


# ------------------------------------------------------ AC-2.4.9 零副作用


def test_ac_2_4_9_limit_failure_leaves_no_trace(app):
    """AC-2.4.9：LIMIT_EXCEEDED 失败前后，loans 全行与 items 全字段逐字段一致。"""
    client = app.test_client()
    client_login(client, STUDENT_A)
    u = user_pk(STUDENT_A)
    for held in (1, 2, 3):
        seed_active_loan(u, held)

    loans_before = direct_query("SELECT * FROM loans ORDER BY id")
    items_before = direct_query("SELECT * FROM items ORDER BY id")
    response = client.post("/borrow", data={"item_id": "4"})
    assert response.status_code == 409
    assert "LIMIT_EXCEEDED" in response.get_data(as_text=True)

    assert direct_query("SELECT * FROM loans ORDER BY id") == loans_before
    assert direct_query("SELECT * FROM items ORDER BY id") == items_before


# ------------------------------------------------------ AC-2.4.10 无角色豁免


def test_ac_2_4_10_admin_same_limit_no_role_branch(app):
    """AC-2.4.10（D-012）：管理员第 4 件同样 409；限额逻辑检索 role 命中 0。"""
    client = app.test_client()
    client_login(client, ADMIN_SID)
    admin = user_pk(ADMIN_SID)
    for held in (1, 2, 3):
        seed_active_loan(admin, held)

    response = client.post("/borrow", data={"item_id": "4"})
    assert response.status_code == 409
    assert ERROR_MESSAGES["LIMIT_EXCEEDED"] in response.get_data(as_text=True)

    loans_source = (REPO_ROOT / "services" / "loans.py").read_text(encoding="utf-8")
    assert re.search(r"\brole\b", loans_source) is None, "限额逻辑不得出现 role 分支"
