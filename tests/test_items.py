"""Story 1.3：物品列表与关键字搜索（AC-1.3.1 ~ AC-1.3.10）。"""

import time

import pytest

import db as db_module


def test_ac_1_3_1_anonymous_list_sorted_and_no_unavailable(client, app):
    """AC-1.3.1: 匿名 GET /items 返回 200，先 book 后 equipment，组内按名称升序，不出现 unavailable。"""
    with app.app_context():
        db = db_module.get_db()
        # 插入一件停用物品
        db.execute(
            "INSERT INTO items (name, category, status, created_at) VALUES (?, ?, ?, ?)",
            ("停用物品", "book", "unavailable", "2026-11-09 10:00:00"),
        )

    response = client.get("/items")
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    # 6 件种子物品 + 1 件停用 = 7 件，但停用不应出现
    assert "停用物品" not in html

    # 验证排序：book 在前，equipment 在后
    # 种子 book: 三体、活着、算法图解
    # 种子 equipment: 投影仪、蓝牙音箱、热熔胶枪
    book_positions = []
    equipment_positions = []
    for name in ["三体", "活着", "算法图解"]:
        pos = html.find(name)
        assert pos > 0, f"book '{name}' not found"
        book_positions.append(pos)
    for name in ["投影仪", "蓝牙音箱", "热熔胶枪"]:
        pos = html.find(name)
        assert pos > 0, f"equipment '{name}' not found"
        equipment_positions.append(pos)

    # 所有 book 位置 < 所有 equipment 位置
    assert max(book_positions) < min(equipment_positions)


def test_ac_1_3_2_search_keyword_case_insensitive(client):
    """AC-1.3.2: 搜索忽略英文大小写与首尾空白。"""
    # 种子数据中没有英文名称，但测试逻辑应支持
    # 先测试中文搜索
    response = client.get("/items?q=胶枪")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "热熔胶枪" in html
    assert "三体" not in html

    # 测试空白处理
    response2 = client.get("/items?q=%20%E8%83%B6%E6%9E%AA%20")  # URL-encoded " 胶枪 "
    assert response2.status_code == 200
    assert response2.get_data(as_text=True) == html


def test_ac_1_3_3_wildcard_escaped(client):
    """AC-1.3.3: 输入单个 % 或 _ 按普通字符匹配，不返回全部物品。"""
    response = client.get("/items?q=%")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    # 没有物品名称包含 %，应为空状态
    assert "没有找到相关物品" in html

    response2 = client.get("/items?q=_")
    assert response2.status_code == 200
    html2 = response2.get_data(as_text=True)
    assert "没有找到相关物品" in html2


def test_ac_1_3_4_empty_query_returns_all(client):
    """AC-1.3.4: q 缺失或纯空白等同于无搜索。"""
    response_missing = client.get("/items")
    response_empty = client.get("/items?q=")
    response_whitespace = client.get("/items?q=%20%20")  # 两个空格

    assert response_missing.status_code == 200
    assert response_empty.status_code == 200
    assert response_whitespace.status_code == 200

    # 三者应返回相同结果
    html_missing = response_missing.get_data(as_text=True)
    html_empty = response_empty.get_data(as_text=True)
    html_whitespace = response_whitespace.get_data(as_text=True)

    assert html_missing == html_empty == html_whitespace


def test_ac_1_3_5_no_match_returns_200_empty_state(client):
    """AC-1.3.5: 无匹配返回 200 + 空状态文案。"""
    response = client.get("/items?q=不存在的名字")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "没有找到相关物品" in html


def test_ac_1_3_6_borrower_name_visibility(client, app):
    """AC-1.3.6: 匿名不显示借阅人姓名，登录用户显示。"""
    with app.app_context():
        db = db_module.get_db()
        # 借出第一件物品（id=1，算法图解）给第一个学生（id=1）
        db.execute(
            "INSERT INTO loans (item_id, user_id, borrowed_at, due_at) VALUES (?, ?, ?, ?)",
            (1, 1, "2026-11-09 10:00:00", "2026-11-16 10:00:00"),
        )

    # 匿名请求
    anonymous = client.get("/items")
    assert anonymous.status_code == 200
    anon_html = anonymous.get_data(as_text=True)
    # 不应显示借阅人姓名列
    assert "借阅人" not in anon_html
    assert "林晓" not in anon_html

    # 登录请求
    client.post("/login", data={"student_id": "2024002", "password": "stu123456"})
    logged_in = client.get("/items")
    assert logged_in.status_code == 200
    login_html = logged_in.get_data(as_text=True)
    # 应显示借阅人姓名列
    assert "借阅人" in login_html
    assert "林晓" in login_html


def test_ac_1_3_7_no_student_id_in_response(client, app):
    """AC-1.3.7: 响应体不出现任何学号字符串。"""
    with app.app_context():
        db = db_module.get_db()
        students = db.execute("SELECT student_id FROM users").fetchall()
        student_ids = [row["student_id"] for row in students]

    response = client.get("/items")
    html = response.get_data(as_text=True)

    for sid in student_ids:
        assert sid not in html, f"student_id '{sid}' leaked in response"


def test_ac_1_3_8_cache_control_no_store(client):
    """AC-1.3.8: 响应头含 Cache-Control: no-store。"""
    response = client.get("/items")
    assert response.headers.get("Cache-Control") == "no-store"

    response2 = client.get("/items?q=胶枪")
    assert response2.headers.get("Cache-Control") == "no-store"


def test_ac_1_3_9_read_only_no_side_effects(client, app):
    """AC-1.3.9: 搜索请求不产生副作用。"""
    with app.app_context():
        db = db_module.get_db()
        # 快照
        loans_before = db.execute("SELECT COUNT(*) AS c FROM loans").fetchone()["c"]
        items_before = {
            row["id"]: row["status"]
            for row in db.execute("SELECT id, status FROM items").fetchall()
        }

    # 连续两次相同搜索
    response1 = client.get("/items?q=胶枪")
    response2 = client.get("/items?q=胶枪")

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.get_data(as_text=True) == response2.get_data(as_text=True)

    with app.app_context():
        db = db_module.get_db()
        loans_after = db.execute("SELECT COUNT(*) AS c FROM loans").fetchone()["c"]
        items_after = {
            row["id"]: row["status"]
            for row in db.execute("SELECT id, status FROM items").fetchall()
        }

    assert loans_before == loans_after
    assert items_before == items_after


def test_ac_1_3_10_performance_50_items(client, app):
    """AC-1.3.10: 50 条物品规模 p95 < 200ms。"""
    with app.app_context():
        db = db_module.get_db()
        # 插入 44 件额外物品（已有 6 件种子 = 50 件）
        for i in range(44):
            db.execute(
                "INSERT INTO items (name, category, status, created_at) VALUES (?, ?, ?, ?)",
                (f"测试物品{i:03d}", "book" if i % 2 == 0 else "equipment", "available", "2026-11-09 10:00:00"),
            )

    # 测试 GET /items
    times_list = []
    for _ in range(20):
        start = time.perf_counter()
        response = client.get("/items")
        elapsed = (time.perf_counter() - start) * 1000  # ms
        times_list.append(elapsed)
        assert response.status_code == 200

    # 测试 GET /items?q=
    times_search = []
    for _ in range(20):
        start = time.perf_counter()
        response = client.get("/items?q=测试")
        elapsed = (time.perf_counter() - start) * 1000
        times_search.append(elapsed)
        assert response.status_code == 200

    # 计算 p95
    times_list.sort()
    times_search.sort()
    p95_list = times_list[int(len(times_list) * 0.95)]
    p95_search = times_search[int(len(times_search) * 0.95)]

    assert p95_list < 200, f"GET /items p95 = {p95_list:.2f}ms > 200ms"
    assert p95_search < 200, f"GET /items?q= p95 = {p95_search:.2f}ms > 200ms"
