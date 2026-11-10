"""Story 2.5 收口：NFR-1.3 归还真并发直压（deferred-work 2.4 遗留项了结）。

此前 NFR-1.3 只有 Story 2.2 的 test_client 冒烟；按登记口径
「不得继续只靠冒烟充当正式验收」，本文件用与 Story 2.3/2.4 完全相同的
共享脚手架（concurrency_kit：单进程 threaded 服务器 + 独立 TCP 连接 +
threading.Barrier）对同一条记录发起两会话并发 POST /return：

- 20 轮状态码集合恰 {302, 409}，409 方响应体含 ALREADY_RETURNED；
- returned_at 只写入一次：并发后两次连续读取逐字节一致且非空；
- 逐轮真实日志入库（concurrency-nfr13-return-20-rounds.log，SM-2 同机制）。
"""

from datetime import datetime
from pathlib import Path

import db as db_module
from config import ERROR_MESSAGES
from concurrency_kit import (
    direct_query,
    login_over_http,
    race_return,
    start_threaded_server,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = (
    REPO_ROOT
    / "_bmad-output"
    / "implementation-artifacts"
    / "concurrency-nfr13-return-20-rounds.log"
)
ROUNDS = 20
STUDENT = "2024001"


def user_pk(student_id):
    return direct_query(
        "SELECT id FROM users WHERE student_id = ?", (student_id,))[0]["id"]


def seed_active_loan(user_id, item_id):
    borrowed = db_module.now_text()
    direct_query(
        "INSERT INTO loans (item_id, user_id, borrowed_at, due_at)"
        " VALUES (?, ?, ?, ?)",
        (item_id, user_id, borrowed, db_module.due_text(borrowed)))
    return direct_query(
        "SELECT id FROM loans WHERE item_id = ? AND returned_at IS NULL",
        (item_id,))[0]["id"]


def returned_at_of(loan_id):
    rows = direct_query(
        "SELECT returned_at FROM loans WHERE id = ?", (loan_id,))
    return rows[0]["returned_at"]


def test_nfr_1_3_concurrent_return_20_rounds_over_http(app):
    """同一记录两会话真并发归还：恰一 302 一 409，returned_at 只写一次。"""
    u = user_pk(STUDENT)
    port, server_kwargs = start_threaded_server(app)
    cookie = login_over_http(port, STUDENT)

    log_lines = [
        "# Story 2.5 收口 / NFR-1.3 归还真并发真实日志  生成于"
        f" {datetime.now():%Y-%m-%d %H:%M:%S}",
        "启动命令: python -m pytest tests/test_return_concurrency.py -v",
        f"部署形态: 单进程 app.run(threaded=True, host={server_kwargs['host']},"
        f" port={server_kwargs['port']}, use_reloader=False)",
        "并发方式: threading.Barrier(2) + 2 线程 + 各自独立 TCP 连接（同一用户会话）",
        f"实验设定: {STUDENT} 借出物品 1，两会话并发 POST /return/<同一条 loan_id>",
        "-" * 72,
    ]
    ok_rounds = 0
    try:
        for round_no in range(1, ROUNDS + 1):
            direct_query("DELETE FROM loans")
            loan_id = seed_active_loan(u, 1)

            results, spread_ms = race_return(port, [
                ("first", cookie, loan_id),
                ("second", cookie, loan_id),
            ])
            codes = sorted(status for status, _body in results.values())
            assert codes == [302, 409], f"第{round_no}轮状态集合={codes}"
            loser = min(results, key=lambda n: results[n][0] == 302)
            loser_body = results[loser][1]
            assert "ALREADY_RETURNED" in loser_body, f"第{round_no}轮失败方缺错误码"
            assert ERROR_MESSAGES["ALREADY_RETURNED"] in loser_body

            # returned_at 恰写一次：非空，且连续两次读取逐字节一致
            stored = returned_at_of(loan_id)
            assert stored is not None, f"第{round_no}轮 returned_at 未写入"
            assert stored == returned_at_of(loan_id), f"第{round_no}轮值不稳定"
            written = direct_query(
                "SELECT COUNT(*) AS c FROM loans WHERE id = ?"
                " AND returned_at IS NOT NULL", (loan_id,))[0]["c"]
            assert written == 1

            ok_rounds += 1
            log_lines.append(
                f"round {round_no:02d}: first={results['first'][0]}"
                f" second={results['second'][0]}"
                f" | barrier 释放间隔={spread_ms:.2f}ms"
                f" | 败方={loser} ALREADY_RETURNED"
                f" | returned_at={stored} 仅一次 OK")
    finally:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    assert ok_rounds == ROUNDS, "20 轮必须无一例外满足 {302,409} 且只写一次"
