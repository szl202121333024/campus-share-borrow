"""Story 3.4 / NFR-1.4：并发结束后的派生态 ⇔ 借阅记录交叉比对（AC-3.4.7）。

NFR-1.4 要证明的不是「每个并发请求各自返回了什么」，而是**并发结束后的系统
自洽**：列表渲染出的状态必须与 `loans` 表里未归还记录的事实严格对应。

- 「有未归还记录却显示可借」= 别人正在借的物品被当成可借（超卖入口）；
- 「没有未归还记录却显示在借」= 物品被凭空锁死（假占位）。

两种中间态都不允许出现，而且这条判据对**每一件物品**成立，不只是被测的那一件，
所以每轮结束都做一次全表交叉比对（学生列表 / 我的借阅 / 管理列表 三张表 ⇔ SQL）。

两段实验都在真实部署形态下进行（单进程 `app.run(threaded=True)`，每个线程
独立 TCP 连接 + 独立会话 cookie，`threading.Barrier` 对齐后同时发出）：

1. **借阅对抗**（复用 Story 2.3 的 20 轮实验）：两个学生抢借同一件物品；
2. **四操作交叉**（本故事新增的高压场景）：借阅、归还、删除、停用四个操作
   同时打向同一件物品 —— 这是四条写路径第一次在同一瞬间相遇：借阅只写
   `loans`、归还只写 `loans`、删除写 `items` + `loans`、停用只写 `items.status`。
   无论数据库把四者串行化成哪种顺序，结束后都不许留下与事实不符的渲染态。

本文件在 tests/ 内直接读库属白盒脚手架（与 concurrency_kit 同口径）。
"""

from datetime import datetime

import db as db_module
from concurrency_kit import (
    direct_query,
    items_snapshot,
    login_over_http,
    race_post,
    race_request,
    seed_password,
    start_threaded_server,
    write_evidence_log,
)
from page_probe import STATE_COLUMN_MY_LOANS, state_map

ADMIN = "A001"
STUDENT_A = "2024001"
STUDENT_B = "2024002"
ROUNDS = 20

FOUR_WAY_LOG = "concurrency-story34-nfr14-four-way-20-rounds.log"
BORROW_RACE_LOG = "concurrency-story34-nfr14-borrow-crosscheck-20-rounds.log"

# 借阅路径 409 的合法错误码：物品已被借出 / 物品已停用 / 本人额度已满
BORROW_CONFLICT_CODES = ("ALREADY_BORROWED", "ITEM_UNAVAILABLE", "LIMIT_EXCEEDED")


# ---------------------------------------------------------------- 基础设施


def _login_client(app, student_id):
    client = app.test_client()
    response = client.post(
        "/login",
        data={"student_id": student_id, "password": seed_password(student_id)},
    )
    assert response.status_code == 302, f"{student_id} 登录应 302"
    return client


def _prepare_clients(app):
    """每轮都要读三个页面，会话复用（登录一次，省掉 PBKDF2 校验开销）。"""
    return {
        STUDENT_A: _login_client(app, STUDENT_A),
        STUDENT_B: _login_client(app, STUDENT_B),
        ADMIN: _login_client(app, ADMIN),
    }


def _page(client, path="/items"):
    response = client.get(path)
    assert response.status_code == 200, (path, response.status_code)
    return response.get_data(as_text=True)


def _count(sql, params=()):
    return direct_query(sql, params)[0]["c"]


def _insert_item(app, name, status_value="available"):
    with app.app_context():
        cursor = db_module.get_db().execute(
            "INSERT INTO items (name, category, status, created_at)"
            " VALUES (?, 'equipment', ?, '2026-11-01 09:00:00')",
            (name, status_value),
        )
        return cursor.lastrowid


def _insert_loan(app, item_id, user_pk=1):
    with app.app_context():
        cursor = db_module.get_db().execute(
            "INSERT INTO loans (item_id, user_id, borrowed_at, due_at)"
            " VALUES (?, ?, '2026-11-10 09:00:00', '2026-11-17 09:00:00')",
            (item_id, user_pk),
        )
        return cursor.lastrowid


def _item_status(app, item_id):
    with app.app_context():
        row = db_module.get_db().execute(
            "SELECT status FROM items WHERE id = ?", (item_id,)
        ).fetchone()
    return None if row is None else row["status"]


def _release_all_loans():
    """轮间复位：把所有未归还记录标记归还，恢复借阅额度（脚手架行为，非产品逻辑）。"""
    direct_query(
        "UPDATE loans SET returned_at = ? WHERE returned_at IS NULL",
        (db_module.now_text(),),
    )


# ---------------------------------------------------------------- 交叉比对判据


def _sql_truth():
    """数据库事实（独立于应用层的直连 SQL）：物品名 → (存储态, 未归还条数)。"""
    rows = direct_query(
        "SELECT i.name, i.status,"
        "       (SELECT COUNT(*) FROM loans l"
        "         WHERE l.item_id = i.id AND l.returned_at IS NULL) AS active"
        "  FROM items i ORDER BY i.id"
    )
    return {row["name"]: (row["status"], row["active"]) for row in rows}


def _held_by_student():
    rows = direct_query(
        "SELECT u.student_id, i.name"
        "  FROM loans l"
        "  JOIN items i ON i.id = l.item_id"
        "  JOIN users u ON u.id = l.user_id"
        " WHERE l.returned_at IS NULL"
    )
    held = {}
    for row in rows:
        held.setdefault(row["student_id"], set()).add(row["name"])
    return held


def _cross_check(app, tag, clients):
    """三张页面渲染 ⇔ loans 事实，逐物品核对（NFR-1.4 的可执行判据）。"""
    truth = _sql_truth()

    # 0) 不存在指向已删除物品的在借记录（删除路径不得留下孤儿）
    orphans = _count(
        "SELECT COUNT(*) AS c FROM loans l"
        "  LEFT JOIN items i ON i.id = l.item_id WHERE i.id IS NULL"
    )
    assert orphans == 0, f"{tag}: {orphans} 条借阅记录指向已删除物品"

    # 0b) 同一物品至多 1 条未归还记录（唯一索引的另一面）
    for name, (_status_value, active) in truth.items():
        assert active in (0, 1), f"{tag}: {name} 有 {active} 条未归还记录"

    # 1) 学生列表：可见集合 = 非停用物品；每行展示态 ⇔ 未归还条数
    visible = state_map(_page(app.test_client()))
    expected_visible = {
        name for name, (status_value, _n) in truth.items()
        if status_value != "unavailable"
    }
    assert set(visible) == expected_visible, (
        f"{tag}: 学生列表可见集合与库不符 "
        f"多={sorted(set(visible) - expected_visible)} "
        f"少={sorted(expected_visible - set(visible))}"
    )
    for name, (status_value, active) in truth.items():
        if status_value == "unavailable":
            continue
        expected = "在借" if active else "可借"
        assert visible[name] == expected, (
            f"{tag}: 「{name}」渲染为「{visible[name]}」，"
            f"但未归还记录={active}（NFR-1.4 中间态）"
        )

    # 2) 我的借阅：每个学生的行集合 ⇔ 该学生的未归还记录
    held = _held_by_student()
    for student_id in (STUDENT_A, STUDENT_B):
        mine = set(state_map(_page(clients[student_id], "/my-loans"),
                             STATE_COLUMN_MY_LOANS))
        assert mine == held.get(student_id, set()), (
            f"{tag}: {student_id} 我的借阅与库不符 "
            f"多={sorted(mine - held.get(student_id, set()))} "
            f"少={sorted(held.get(student_id, set()) - mine)}"
        )

    # 3) 管理列表：全量可见，优先级 unavailable > borrowed > available
    admin_states = state_map(_page(clients[ADMIN], "/admin/items"))
    assert set(admin_states) == set(truth), f"{tag}: 管理列表集合与库不符"
    for name, (status_value, active) in truth.items():
        expected = ("已停用" if status_value == "unavailable"
                    else "在借" if active else "可借")
        assert admin_states[name] == expected, (
            f"{tag}: 管理列表「{name}」={admin_states[name]}，"
            f"存储态={status_value} 未归还={active}"
        )

    return truth


# ---------------------------------------------------------------- AC-3.4.7 借阅对抗


def test_nfr_1_4_borrow_race_list_matches_counts_20_rounds(app):
    """AC-3.4.7：复用 Story 2.3 的 20 轮抢借实验，每轮结束立即交叉比对。"""
    target_name = "NFR14 抢借目标"
    target = _insert_item(app, target_name)
    items_before = items_snapshot()

    port, server_kwargs = start_threaded_server(app)
    cookie_a = login_over_http(port, STUDENT_A)
    cookie_b = login_over_http(port, STUDENT_B)
    clients = _prepare_clients(app)

    log_lines = [
        f"# Story 3.4 / NFR-1.4 借阅对抗交叉比对真实日志"
        f"  生成于 {datetime.now():%Y-%m-%d %H:%M:%S}",
        "启动命令: python -m pytest tests/test_nfr14_cross_check.py -v -k race",
        f"部署形态: 单进程 app.run(threaded=True, host={server_kwargs['host']},"
        f" port={server_kwargs['port']}, use_reloader=False)",
        "并发方式: threading.Barrier(2) + 2 线程 + 各自独立 TCP 连接与会话 cookie",
        f"抢借物品: {target_name} (id={target}), 参与者: {STUDENT_A} vs {STUDENT_B}",
        "判据: 每轮结束交叉比对 学生列表/我的借阅/管理列表 ⇔ loans 未归还计数",
        "-" * 72,
    ]
    try:
        for round_no in range(1, ROUNDS + 1):
            results, spread_ms = race_post(
                port, [("A", cookie_a, target), ("B", cookie_b, target)]
            )
            codes = sorted(status for status, _body in results.values())
            assert codes == [302, 409], f"第{round_no}轮状态集合={codes}"
            winner = next(
                name for name, (status, _body) in results.items() if status == 302
            )
            loser = "B" if winner == "A" else "A"
            assert "ALREADY_BORROWED" in results[loser][1], f"第{round_no}轮失败方错误码"

            active = _count(
                "SELECT COUNT(*) AS c FROM loans"
                " WHERE item_id = ? AND returned_at IS NULL", (target,)
            )
            assert active == 1, f"第{round_no}轮未归还记录={active}"

            truth = _cross_check(app, f"借阅对抗第{round_no}轮", clients)
            # 交叉比对要点：唯一那条未归还记录必须渲染成「在借」，且只属于胜方
            assert truth[target_name] == ("available", 1)
            assert state_map(_page(app.test_client()))[target_name] == "在借"
            winner_id = STUDENT_A if winner == "A" else STUDENT_B
            assert _held_by_student() == {winner_id: {target_name}}, f"第{round_no}轮持有者"

            log_lines.append(
                f"round {round_no:02d}: A({STUDENT_A})={results['A'][0]}"
                f" B({STUDENT_B})={results['B'][0]}"
                f" | barrier 释放间隔={spread_ms:.2f}ms"
                f" | 胜方={winner_id}"
                f" | active_count=1 渲染=在借 交叉比对=一致"
            )
            _release_all_loans()
    finally:
        write_evidence_log(BORROW_RACE_LOG, log_lines)

    # 借阅与归还都只写 loans：items 表逐字段不变
    assert items_snapshot() == items_before


# ---------------------------------------------------------------- AC-3.4.7 四操作交叉


def test_nfr_1_4_four_operation_race_never_leaves_intermediate_state(app):
    """借阅 / 归还 / 删除 / 停用 四个操作同时打向同一件物品，20 轮无中间态。"""
    port, server_kwargs = start_threaded_server(app)
    cookie_admin = login_over_http(port, ADMIN)
    cookie_return = login_over_http(port, STUDENT_A)
    cookie_borrow = login_over_http(port, STUDENT_B)
    clients = _prepare_clients(app)

    log_lines = [
        f"# Story 3.4 / NFR-1.4 四操作交叉真实日志"
        f"  生成于 {datetime.now():%Y-%m-%d %H:%M:%S}",
        "启动命令: python -m pytest tests/test_nfr14_cross_check.py -v -k four_operation",
        f"部署形态: 单进程 app.run(threaded=True, host={server_kwargs['host']},"
        f" port={server_kwargs['port']}, use_reloader=False)",
        "并发方式: threading.Barrier(4) + 4 线程 + 各自独立 TCP 连接"
        f"（管理员 {ADMIN} / 借阅者 {STUDENT_A} / 借阅者 {STUDENT_B}）",
        "实验设定: 每轮新建一件物品并预置 1 条未归还记录（持有人 = 学生A）；"
        "同时 POST /borrow、POST /return/<loan_id>、POST /admin/items/<id>/delete、"
        "POST /admin/items/<id>/unavailable",
        "判据: 每轮结束交叉比对 学生列表/我的借阅/管理列表 ⇔ loans 未归还计数",
        "-" * 72,
    ]
    try:
        for round_no in range(1, ROUNDS + 1):
            target_name = f"NFR14 四操作目标 {round_no:02d}"
            item_id = _insert_item(app, target_name)
            loan_id = _insert_loan(app, item_id, user_pk=1)

            results, spread_ms = race_request(
                port,
                [
                    ("borrow", cookie_borrow, "/borrow", {"item_id": item_id}),
                    ("return", cookie_return, f"/return/{loan_id}", {}),
                    ("delete", cookie_admin, f"/admin/items/{item_id}/delete", {}),
                    ("disable", cookie_admin, f"/admin/items/{item_id}/unavailable", {}),
                ],
            )
            statuses = {name: status for name, (status, _body) in results.items()}

            # 1) 四条写路径都不许 5xx：任何异常都必须落成确定的状态码
            assert all(code != 500 for code in statuses.values()), (
                round_no, statuses
            )
            # 2) 每条路径的状态码必须在语义允许的集合内
            assert statuses["return"] == 302, (round_no, statuses)
            assert statuses["borrow"] in (302, 404, 409), (round_no, statuses)
            assert statuses["delete"] in (302, 409), (round_no, statuses)
            assert statuses["disable"] in (302, 404), (round_no, statuses)
            if statuses["borrow"] == 409:
                assert any(code in results["borrow"][1]
                           for code in BORROW_CONFLICT_CODES), (round_no, statuses)
            if statuses["delete"] == 409:
                assert "ITEM_IN_BORROW" in results["delete"][1], (round_no, statuses)

            # 3) 删除的成败与物品是否存在必须一一对应（不许「说删了但还在」）
            deleted = _count(
                "SELECT COUNT(*) AS c FROM items WHERE id = ?", (item_id,)
            ) == 0
            assert deleted == (statuses["delete"] == 302), (round_no, statuses)
            active = _count(
                "SELECT COUNT(*) AS c FROM loans"
                " WHERE item_id = ? AND returned_at IS NULL", (item_id,)
            )
            if deleted:
                # 物品已被删除：借阅只可能「找不到物品」(404) 或「已被停用/已借出」(409)，
                # 绝不允许 302——借成功却查不到物品就是最严重的那种中间态。
                assert statuses["borrow"] in (404, 409), (round_no, statuses)
                assert _count(
                    "SELECT COUNT(*) AS c FROM loans WHERE item_id = ?", (item_id,)
                ) == 0, f"第{round_no}轮物品已删但借阅记录残留"
            elif statuses["borrow"] == 302:
                # 借成功 ⇒ 归还已经落地、物品还在 ⇒ 删除必然被在借拦截
                assert statuses["delete"] == 409, (round_no, statuses)
                assert active == 1, (round_no, active)

            # 4) 全表交叉比对：三张表 ⇔ loans 事实（核心断言）
            _cross_check(app, f"四操作第{round_no}轮", clients)

            log_lines.append(
                f"round {round_no:02d}: borrow={statuses['borrow']}"
                f" return={statuses['return']} delete={statuses['delete']}"
                f" disable={statuses['disable']}"
                f" | barrier 释放间隔={spread_ms:.2f}ms"
                f" | item={'已删除' if deleted else '保留'}"
                f" active={active} | 交叉比对=一致"
            )
            _release_all_loans()
    finally:
        write_evidence_log(FOUR_WAY_LOG, log_lines)
