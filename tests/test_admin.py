"""Story 3.1：管理员新增物品与管理列表（AC-3.1.1 ~ 3.1.8 + D-012 结构守卫）。

并发与借贷数据的构造口径遵循 epics.md「史诗独立性」条款：需要「有在借记录」
时用 SQL 直接构造，不调用借阅接口。
"""

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import db as db_module

SOURCE_ROOT = Path(__file__).resolve().parent.parent

ADMIN_ID = ("A001", "admin123456")
STUDENT_ID = ("2024001", "stu123456")


def _login(client, student_id, password):
    return client.post("/login", data={"student_id": student_id, "password": password})


def _login_admin(client):
    response = _login(client, *ADMIN_ID)
    assert response.status_code == 302
    return response


def _items_snapshot(app):
    with app.app_context():
        rows = db_module.get_db().execute(
            "SELECT id, name, category, status, created_at FROM items ORDER BY id"
        ).fetchall()
    return [tuple(row) for row in rows]


# ---------- AC-3.1.1 未登录：GET 与 POST 均 302 → /login?next=/admin/items ----------


def test_ac_3_1_1_unauthenticated_get_redirects_to_login_with_next(client):
    response = client.get("/admin/items")

    assert response.status_code == 302
    location = urlparse(response.headers["Location"])
    assert location.path == "/login"
    assert parse_qs(location.query)["next"] == ["/admin/items"]


def test_ac_3_1_1_unauthenticated_post_redirects_without_creating_item(client, app):
    before = _items_snapshot(app)

    response = client.post(
        "/admin/items", data={"name": "越权新增", "category": "book"}
    )

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/login"
    assert _items_snapshot(app) == before


# ---------- AC-3.1.2 学生：GET/POST 一律 403 FORBIDDEN，零数据变更 ----------


def test_ac_3_1_2_student_get_is_forbidden_shows_admin_message(client):
    _login(client, *STUDENT_ID)

    response = client.get("/admin/items")

    assert response.status_code == 403
    html = response.get_data(as_text=True)
    assert "FORBIDDEN" in html
    assert "仅管理员可访问" in html


def test_ac_3_1_2_student_post_is_forbidden_with_unchanged_items(client, app):
    _login(client, *STUDENT_ID)
    before = _items_snapshot(app)

    response = client.post(
        "/admin/items", data={"name": "学生偷加", "category": "equipment"}
    )

    assert response.status_code == 403
    assert "FORBIDDEN" in response.get_data(as_text=True)
    assert _items_snapshot(app) == before


# ---------- AC-3.1.3 管理员新增成功：302 + 已添加 + status=available + 立即可搜 ----------


def test_ac_3_1_3_admin_creates_item_and_it_is_immediately_searchable(client, app):
    _login_admin(client)
    before = _items_snapshot(app)

    response = client.post(
        "/admin/items", data={"name": "热熔胶枪 #3", "category": "equipment"}
    )

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/admin/items"

    # PRG 落地页 flash「已添加」（一次 GET 消费 flash，不得二次 GET）
    landing = client.get("/admin/items")
    assert landing.status_code == 200
    assert "已添加" in landing.get_data(as_text=True)

    # 新增恰好 1 条，status 默认 available（AC-3.1.3 原文含「#」字面名称）
    after = _items_snapshot(app)
    assert len(after) == len(before) + 1
    created = [row for row in after if row[1] == "热熔胶枪 #3"]
    assert len(created) == 1 and created[0][3] == "available"

    # 立刻可被学生端搜索命中
    search = client.get("/items", query_string={"q": "胶枪"})
    assert search.status_code == 200
    html = search.get_data(as_text=True)
    assert "热熔胶枪 #3" in html


def test_ac_3_1_3_create_strips_surrounding_whitespace(client, app):
    _login_admin(client)

    response = client.post(
        "/admin/items", data={"name": "  蓝牙音箱（备用）  ", "category": "equipment"}
    )

    assert response.status_code == 302
    names = [row[1] for row in _items_snapshot(app)]
    assert "蓝牙音箱（备用）" in names


# ---------- AC-3.1.4 名称校验：空/纯空格/51 字符合 → 400；50 字符合边界通过 ----------


def test_ac_3_1_4_blank_names_rejected_with_400_invalid_input(client, app):
    _login_admin(client)
    before = _items_snapshot(app)

    for raw_name in ("", "     ", "\t\n "):
        response = client.post(
            "/admin/items", data={"name": raw_name, "category": "book"}
        )
        assert response.status_code == 400, raw_name
        html = response.get_data(as_text=True)
        assert "INVALID_INPUT" in html

    missing_name = client.post("/admin/items", data={"category": "book"})
    assert missing_name.status_code == 400
    assert _items_snapshot(app) == before


def test_ac_3_1_4_name_length_boundary_50_ok_51_rejected(client, app):
    _login_admin(client)
    before = _items_snapshot(app)

    too_long = client.post(
        "/admin/items", data={"name": "名" * 51, "category": "book"}
    )
    assert too_long.status_code == 400
    assert "INVALID_INPUT" in too_long.get_data(as_text=True)
    assert _items_snapshot(app) == before

    exactly_50 = client.post(
        "/admin/items", data={"name": "名" * 50, "category": "book"}
    )
    assert exactly_50.status_code == 302
    padded = client.post(
        "/admin/items", data={"name": "  " + "字" * 50 + "  ", "category": "book"}
    )
    assert padded.status_code == 302
    names = [row[1] for row in _items_snapshot(app)]
    assert "名" * 50 in names and "字" * 50 in names


# ---------- AC-3.1.5 类别校验：book/equipment 之外（含空值/大小写变体）400 ----------


def test_ac_3_1_5_category_outside_enum_rejected(client, app):
    _login_admin(client)
    before = _items_snapshot(app)

    for category in ("", "furniture", "Book", "BOOK", "book "):
        response = client.post(
            "/admin/items", data={"name": "类别越界测试", "category": category}
        )
        assert response.status_code == 400, category
        assert "INVALID_INPUT" in response.get_data(as_text=True)

    missing_category = client.post("/admin/items", data={"name": "缺类别"})
    assert missing_category.status_code == 400
    assert _items_snapshot(app) == before


# ---------- AC-3.1.6 名称允许重复：两条同名记录，各自独立 id ----------


def test_ac_3_1_6_duplicate_names_allowed_with_independent_ids(client, app):
    _login_admin(client)

    first = client.post("/admin/items", data={"name": "热熔胶枪", "category": "equipment"})
    second = client.post("/admin/items", data={"name": "热熔胶枪", "category": "equipment"})

    assert first.status_code == second.status_code == 302
    rows = [row for row in _items_snapshot(app) if row[1] == "热熔胶枪"]
    # 种子已有 1 条「热熔胶枪」，本用例再加 2 条 → 共 3 条，id 互不相同
    assert len(rows) == 3
    assert len({row[0] for row in rows}) == 3


# ---------- AC-3.1.7 管理列表：全部物品 + 停用标注「已停用」+ 在借标注在借人 ----------


def test_ac_3_1_7_admin_list_shows_all_items_with_state_annotations(client, app):
    _login_admin(client)
    with app.app_context():
        conn = db_module.get_db()
        conn.execute(
            "UPDATE items SET status = 'unavailable' WHERE name = '投影仪'"
        )
        conn.execute(
            "INSERT INTO loans (item_id, user_id, borrowed_at, due_at, returned_at)"
            " VALUES ("
            "  (SELECT id FROM items WHERE name = '三体'),"
            "  (SELECT id FROM users WHERE student_id = '2024001'),"
            "  '2026-11-01 10:00:00', '2026-11-08 10:00:00', NULL)"
        )

    response = client.get("/admin/items")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    html = response.get_data(as_text=True)
    # 全部物品可见，含停用项
    for name in ("算法图解", "活着", "三体", "热熔胶枪", "蓝牙音箱", "投影仪"):
        assert name in html
    # 停用项明确标注；在借项标注借阅人姓名（管理端可见）
    assert "已停用" in html
    assert "林晓" in html
    # 学生端确认看不到停用项（对照 AC-3.3.2 前置语义）
    student_page = client.get("/items").get_data(as_text=True)
    assert "投影仪" not in student_page


# ---------- AC-3.1.8 结构约束：不写 borrowed 状态；SSR 表单 POST，无 JSON/fetch ----------


def _python_sources(subdir):
    return sorted((SOURCE_ROOT / subdir).glob("*.py"))


# 注释/docstring 里提到 `grep "UPDATE items"` 只是文档，不构成一条写语句
_DOCSTRING = re.compile(r'""".*?"""', re.S)


def _code_without_docstrings(path):
    return _DOCSTRING.sub("", path.read_text(encoding="utf-8"))


def _items_status_update_statements():
    """收集 services/ 与 routes/ 里所有 `UPDATE items` 语句（文件相对路径 + 语句）。"""
    hits = []
    for subdir in ("services", "routes"):
        for path in _python_sources(subdir):
            text = _code_without_docstrings(path)
            for match in re.finditer(r"UPDATE\s+items[^\n]*", text, re.IGNORECASE):
                hits.append(
                    (f"{subdir}/{path.name}", match.group(0))
                )
    return hits


def test_ac_3_1_8_source_never_writes_borrowed_into_items_status():
    """AR-4/PC-8：items.status 的取值写入只允许 'available'/'unavailable' 字面量。

    Story 3.1 时本断言要求「services/ 与 routes/ 零 UPDATE items」；Story 3.3/3.4
    依 ADR-007 §2.1 开闸：物品状态的唯一写入者是管理员，允许的写点恰为
    `services/admin.py` 的 `set_unavailable()` 与 `set_available()` 两处
    （AC-3.4.5 的 grep 判据）。开闸不放宽取值集合——'borrowed' 仍零命中。
    """
    hits = _items_status_update_statements()
    # AC-3.4.5：全项目 UPDATE items 恰两处，且都落在管理员服务里（借阅/归还/删除零命中）
    assert [origin for origin, _sql in hits] == ["services/admin.py", "services/admin.py"]
    allowed = re.compile(
        r"UPDATE items SET status = '(available|unavailable)' WHERE id = \?"
    )
    for _origin, sql in hits:
        assert allowed.search(sql), sql
        assert "borrowed" not in sql.lower(), sql

    # INSERT 路径同样不得写入 'borrowed'
    violations = []
    for path in _python_sources("services") + _python_sources("routes"):
        text = _code_without_docstrings(path)
        for match in re.finditer(
            r"INSERT\s+INTO\s+items.*?[\"']\s*(?:\)|$)", text, re.IGNORECASE | re.DOTALL
        ):
            if "borrowed" in match.group(0):
                violations.append(f"{path.name}: INSERT items with 'borrowed'")
    assert violations == []


def test_ac_3_1_8_admin_form_is_server_rendered_post_without_fetch():
    """AC-3.1.8：表单为 SSR 的 form+POST；无 fetch/XHR/JSON API（ADR-001）。"""
    html = (SOURCE_ROOT / "templates" / "admin_items.html").read_text(encoding="utf-8")
    assert 'method="post"' in html
    assert "fetch(" not in html and "XMLHttpRequest" not in html
    admin_py = (SOURCE_ROOT / "routes" / "admin.py").read_text(encoding="utf-8")
    assert "jsonify" not in admin_py and "request.json" not in admin_py


# ---------- D-012：role 授权判定只存在于蓝图守卫一处（用户三条约束之一） ----------


def test_d_012_role_check_exists_exactly_at_blueprint_guard():
    """全库 role==admin 判定只允许出现在蓝图守卫一处（D-012、PC-10 可 grep 判据）。"""
    pattern = re.compile(r"""\[\s*["']role["']\s*\]\s*[!=]=\s*["']admin["']""")
    hits = {}
    for path in _python_sources("routes") + _python_sources("services"):
        count = len(pattern.findall(path.read_text(encoding="utf-8")))
        if count:
            hits[path.name] = count
    assert hits == {"admin.py": 1}


def test_d_012_admin_blueprint_guard_is_before_request_not_inline():
    """403 必须由 bp.before_request 统一拦截，而不是散落在视图函数体内。"""
    text = (SOURCE_ROOT / "routes" / "admin.py").read_text(encoding="utf-8")
    marker = "@bp.before_request"
    assert marker in text
    guard_section = text.split(marker, 1)[1]
    assert 'if user["role"] != "admin":' in guard_section
    # 视图函数体（守卫之后）不再出现第二处 role 判断
    view_section = guard_section.split("@bp.route", 1)[1]
    assert '"role"' not in view_section


# ---------- 只增不删改（人类裁决）：编辑端点（含 PUT）在 v1 不存在 ----------


def test_edit_endpoint_stays_unregistered_and_put_unsupported(client, app):
    """范围哨兵：编辑功能是人类裁决砍掉的（D-007 无名称快照），永不注册。

    删除（3.2）、停用与恢复上架（3.3/3.4）已各自注册，见 test_admin_delete.py
    与 test_admin_state.py；本哨兵只锁死「无编辑」这一条。
    """
    _login_admin(client)
    before = _items_snapshot(app)
    first_item_id = before[0][0]

    for method, path in (
        ("GET", f"/admin/items/{first_item_id}/edit"),
        ("POST", f"/admin/items/{first_item_id}/edit"),
        ("PUT", f"/admin/items/{first_item_id}"),
        ("PATCH", f"/admin/items/{first_item_id}"),
    ):
        response = client.open(path, method=method)
        assert response.status_code == 404, f"{method} {path}"

    assert _items_snapshot(app) == before


def test_state_change_endpoints_reject_get(client, app):
    """停用/恢复上架只接受 POST：地址栏 GET 不改变任何状态（PRG 写操作口径）。"""
    _login_admin(client)
    before = _items_snapshot(app)
    first_item_id = before[0][0]

    for path in (
        f"/admin/items/{first_item_id}/unavailable",
        f"/admin/items/{first_item_id}/available",
    ):
        assert client.get(path).status_code == 405, path

    assert _items_snapshot(app) == before


def test_items_page_and_quota_behavior_unchanged_after_guard_refactor(client):
    """守卫改造回归哨兵：学生登录态下业务页面照常 200，管理入口仍不可达 403。"""
    _login(client, *STUDENT_ID)
    assert client.get("/items").status_code == 200
    assert client.get("/my-loans").status_code == 200
    assert client.get("/admin/items").status_code == 403


def test_unregistered_admin_paths_never_execute_for_student(client, app):
    """未注册/带尾斜杠的 /admin 路径：学生得到 404（路由不存在，对任何角色一致），
    绝不落入任何管理视图；认证拦截先于路由解析，未登录一律 302。"""
    before = _items_snapshot(app)

    student = _login(client, *STUDENT_ID)
    assert student.status_code == 302
    for path in ("/admin/items/", "/admin/nope"):
        assert client.get(path).status_code == 404, path
        assert client.post(path).status_code == 404, path

    client.post("/logout")
    for path in ("/admin/items/", "/admin/nope"):
        response = client.open(path, method="GET")
        assert response.status_code == 302, path
        assert urlparse(response.headers["Location"]).path == "/login"

    assert _items_snapshot(app) == before
