"""并发测试共享脚手架（Story 2.3 建立，Story 2.4 按约定复用）。

真实部署形态：单进程 `app.run(threaded=True)`，测试线程各自持独立 TCP
连接与独立会话 cookie，在 threading.Barrier 对齐后同时发起请求——
这是「真并发」的最小实现（AC-2.3.9、AC-2.4.1~2.4.3 共用同一机制）。

本文件在 tests/ 内直接使用 sqlite3.connect 属白盒测试脚手架（PC-2 扫描
豁免 tests 目录，与 test_story_1_1_rules 同口径）；被测源码不含第二处连接。
"""

import http.client
import socket
import sqlite3
import threading
import time
from urllib.parse import urlencode

import db as db_module


def seed_password(student_id):
    """从 db.SEED_USERS 取种子口令；测试文件不写死明文凭据。"""
    for sid, _name, _role, password in db_module.SEED_USERS:
        if sid == student_id:
            return password
    raise AssertionError(f"非种子账号: {student_id}")


def direct_connect():
    """测试专用底层直连（绕过 get_db 与 Flask 上下文），白盒证据用。"""
    conn = sqlite3.connect(db_module.DB_PATH, isolation_level=None)
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    return conn


def direct_query(sql, params=()):
    conn = direct_connect()
    try:
        cursor = conn.execute(sql, params)
        if cursor.description is None:  # 写语句（自举已 autocommit）
            return []
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def client_login(client, student_id):
    """test_client 登录：口令一律来自 seed_password，不写死明文。"""
    password = seed_password(student_id)
    response = client.post(
        "/login", data={"student_id": student_id, "password": password})
    assert response.status_code == 302, f"登录应 302，实际 {response.status_code}"


def client_borrow(client, item_id):
    return client.post("/borrow", data={"item_id": str(item_id)})


def login_over_http(port, student_id):
    """走真实 HTTP 登录拿会话 cookie，返回 Set-Cookie 的 name=value 段。"""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    body = urlencode(
        {"student_id": student_id, "password": seed_password(student_id)})
    conn.request("POST", "/login", body=body,
                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    resp = conn.getresponse()
    cookie_header = resp.getheader("Set-Cookie")
    resp.read()
    conn.close()
    assert resp.status == 302, f"登录应 302，实际 {resp.status}"
    assert cookie_header, "登录响应缺少 Set-Cookie"
    return cookie_header.split(";")[0]


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def start_threaded_server(app):
    """按真实部署形态启动：单进程、threaded=True（AC-2.3.9、ADR-005 §6）。"""
    port = free_port()
    server_kwargs = {"host": "127.0.0.1", "port": port,
                     "threaded": True, "use_reloader": False}
    thread = threading.Thread(
        target=lambda: app.run(**server_kwargs), daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            probe = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            probe.request("GET", "/items")
            ready = probe.getresponse().status == 200
            probe.close()
            if ready:
                return port, server_kwargs
        except OSError:
            time.sleep(0.05)
    raise AssertionError("并发测试服务器未能启动")


def race_post(port, specs):
    """specs = [(name, cookie, item_id), ...]：barrier 对齐后同时 POST /borrow。

    每个 worker 新建独立 TCP 连接（不是同一连接上排队）。
    返回 (results, spread_ms)：results[name] = (status, body)；
    spread_ms 为各线程从 barrier 释放到发起请求的最大时间差（毫秒），
    是「同一瞬间打出去」的直接证据。
    """
    barrier = threading.Barrier(len(specs))
    results = {}
    started_at = {}

    def worker(name, cookie, item_id):
        barrier.wait(timeout=15)
        started_at[name] = time.perf_counter()
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
        conn.request("POST", "/borrow",
                     body=urlencode({"item_id": str(item_id)}),
                     headers={"Content-Type": "application/x-www-form-urlencoded",
                              "Cookie": cookie})
        resp = conn.getresponse()
        results[name] = (resp.status, resp.read().decode("utf-8"))
        conn.close()

    threads = [threading.Thread(target=worker, args=spec) for spec in specs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    expected = {name for name, _cookie, _item in specs}
    assert set(results) == expected, "所有并发请求都必须收到响应"
    spread_ms = (max(started_at.values()) - min(started_at.values())) * 1000
    return results, spread_ms


def items_snapshot():
    rows = direct_query("SELECT * FROM items ORDER BY id")
    return [tuple(row.values()) for row in rows]


def item_row_state_text(client, item_name):
    """从 /items 表体中按名称取该物品行的「在借/可借」字样。"""
    page = client.get("/items").get_data(as_text=True)
    body = page.split("<tbody>")[1].split("</tbody>")[0]
    rows = [chunk for chunk in body.split("<tr>") if item_name in chunk]
    assert len(rows) == 1, f"{item_name} 应恰好一行，实际 {len(rows)}"
    if "在借" in rows[0]:
        return "在借"
    assert "可借" in rows[0]
    return "可借"
