"""Story 3.4：四态组合矩阵与派生唯一实现（AC-3.4.4、AC-3.4.6）。

ADR-007 的「存储态 + 派生态」模型只有两个存储取值（available / unavailable），
「在借」由 loans 的未归还记录派生，于是用户可见的状态恰好是 2 × 2 四种组合：

| 组合 | items.status | 未归还记录 | GET /items（学生） | GET /my-loans（借阅者） | GET /admin/items |
|---|---|---|---|---|---|
| A | available   | 无 | 可借（有借阅入口） | 不出现          | 可借   |
| B | available   | 有 | 在借（无借阅入口） | 出现 + 可归还   | 在借   |
| C | unavailable | 无 | 不出现（列表与搜索）| 不出现          | 已停用 |
| D | unavailable | 有 | 不出现（列表与搜索）| 出现 + 可归还   | 已停用 |

四种组合各有独立用例（AC-3.4.4 要求「独立断言」），逐组合核对两个列表；
另有一条矩阵用例把四种组合放进同一个库状态、一次渲染交叉核对——四条渲染
路径（学生列表 / 搜索结果 / 我的借阅 / 管理列表）必须给出同一份判定，
这正是 AC-3.4.6 说的「`list_items_with_state(...)` 是唯一实现」。

数据构造沿用 epics.md「史诗独立性」口径：需要「在借记录」时用 SQL 直接构造，
不依赖 Epic 2 的借阅接口；仅在验证归还链路时调用真实 `POST /return`。
"""

import re
from pathlib import Path

import db as db_module
import routes.admin as admin_route
import routes.items as items_route
import services.items as items_service
from concurrency_kit import seed_password
from page_probe import (
    STATE_COLUMN_MY_LOANS,
    row_of,
    rows_by_name,
    state_map,
)

SOURCE_ROOT = Path(__file__).resolve().parents[1]

STUDENT_A = "2024001"   # 林晓
STUDENT_B = "2024002"   # 陈默
ADMIN = "A001"

# 组合代号 → 物品名称（名称唯一，便于按行定位；不会互为子串前缀的误命中）
NAME_A = "四态A可借无借"
NAME_B = "四态B可借在借"
NAME_C = "四态C停用无借"
NAME_D = "四态D停用在借"

DUE_AT = "2026-11-17 09:00:00"
BORROWED_AT = "2026-11-10 09:00:00"

DOCSTRING = re.compile(r'""".*?"""', re.S)


# ---------------------------------------------------------------- 基础设施


def _client(app, student_id=None):
    """新建会话；给 student_id 时先登录（口令取自 db.SEED_USERS，不写死明文）。"""
    client = app.test_client()
    if student_id is not None:
        response = client.post(
            "/login",
            data={"student_id": student_id, "password": seed_password(student_id)},
        )
        assert response.status_code == 302, f"{student_id} 登录应 302"
    return client


def _page(client, path="/items", query=None):
    response = client.get(path, query_string=query or {})
    assert response.status_code == 200, (path, response.status_code)
    return response.get_data(as_text=True)


def _insert_item(app, name, status_value, category="equipment"):
    with app.app_context():
        cursor = db_module.get_db().execute(
            "INSERT INTO items (name, category, status, created_at)"
            " VALUES (?, ?, ?, '2026-11-01 09:00:00')",
            (name, category, status_value),
        )
        return cursor.lastrowid


def _insert_loan(app, item_id, user_pk, borrowed_at=BORROWED_AT, due_at=DUE_AT):
    """SQL 直接构造一条未归还记录（史诗独立性：不调 /borrow）。"""
    with app.app_context():
        cursor = db_module.get_db().execute(
            "INSERT INTO loans (item_id, user_id, borrowed_at, due_at)"
            " VALUES (?, ?, ?, ?)",
            (item_id, user_pk, borrowed_at, due_at),
        )
        return cursor.lastrowid


def _item_status(app, item_id):
    with app.app_context():
        return db_module.get_db().execute(
            "SELECT status FROM items WHERE id = ?", (item_id,)
        ).fetchone()["status"]


def _sql_truth(app):
    """数据库事实：物品名 → (存储态, 未归还记录条数)，交叉比对的右半边。"""
    with app.app_context():
        rows = db_module.get_db().execute(
            "SELECT i.name, i.status,"
            "       (SELECT COUNT(*) FROM loans l"
            "         WHERE l.item_id = i.id AND l.returned_at IS NULL) AS active"
            "  FROM items i ORDER BY i.id"
        ).fetchall()
    return {row["name"]: (row["status"], row["active"]) for row in rows}


def _assert_loan_state(cell_text):
    """我的借阅的状态列只允许「在借」或「已逾期 N 天」（due 当天不算逾期）。"""
    assert cell_text == "在借" or cell_text.startswith("已逾期"), cell_text


def _strip_docstrings(text):
    """结构断言只看代码，不看注释里被引用的 SQL 字样。"""
    return DOCSTRING.sub("", text)


# ---------------------------------------------------------------- AC-3.4.4 组合 A


def test_combination_1_available_without_loan_shows_available(app):
    """组合 A：available + 无在借 → 学生列表「可借」且有借阅入口；我的借阅为空。"""
    item_id = _insert_item(app, NAME_A, "available")
    anonymous = _client(app)
    student = _client(app, STUDENT_A)

    cells, row_html = row_of(_page(anonymous), NAME_A)
    assert cells[2] == "可借"
    assert "在借" not in cells[2]
    assert "action=\"/borrow\"" not in row_html          # 匿名不渲染操作列

    cells, row_html = row_of(_page(student), NAME_A)
    assert cells[2] == "可借"
    assert 'action="/borrow"' in row_html               # 唯一允许借阅的派生态
    assert f'value="{item_id}"' in row_html

    # 搜索同样命中（学生列表与搜索结果共用同一份派生查询）
    assert NAME_A in _page(anonymous, query={"q": NAME_A})

    # 我的借阅：没有借阅事实 → 不出现，且渲染空状态文案
    my_loans = _page(student, "/my-loans")
    assert NAME_A not in my_loans
    assert "当前没有在借物品" in my_loans

    # 管理列表：可借 + 提供「停用」动作（动作由存储态决定，不由派生态）
    _cells, admin_row = row_of(_page(_client(app, ADMIN), "/admin/items"), NAME_A)
    assert _cells[2] == "可借"
    assert f"/admin/items/{item_id}/unavailable" in admin_row
    assert f"/admin/items/{item_id}/available" not in admin_row


# ---------------------------------------------------------------- AC-3.4.4 组合 B


def test_combination_2_available_with_loan_shows_borrowed(app):
    """组合 B：available + 在借 → 学生列表「在借」（无借阅入口）；借阅者可见可归还。"""
    item_id = _insert_item(app, NAME_B, "available")
    loan_id = _insert_loan(app, item_id, user_pk=1)
    anonymous = _client(app)
    borrower = _client(app, STUDENT_A)
    other = _client(app, STUDENT_B)

    cells, row_html = row_of(_page(anonymous), NAME_B)
    assert cells[2] == "在借"
    assert cells[3] == DUE_AT                          # 应还日期列

    cells, row_html = row_of(_page(borrower), NAME_B)
    assert cells[2] == "在借"
    assert cells[3] == DUE_AT
    assert cells[4] == "林晓"                          # 借阅人列
    assert 'action="/borrow"' not in row_html          # 在借不再提供借阅入口

    my_cells, my_row = row_of(_page(borrower, "/my-loans"), NAME_B)
    _assert_loan_state(my_cells[3])
    assert my_cells[1] == BORROWED_AT
    assert my_cells[2] == DUE_AT
    assert f"/return/{loan_id}" in my_row               # 有归还入口

    assert NAME_B not in _page(other, "/my-loans")      # 他人看不到这条记录

    # 管理列表：在借 + 在借人，动作仍是「停用」（在借物品同样可停用，D-003）
    admin_cells, admin_row = row_of(_page(_client(app, ADMIN), "/admin/items"), NAME_B)
    assert admin_cells[2] == "在借"
    assert admin_cells[4] == "林晓"
    assert f"/admin/items/{item_id}/unavailable" in admin_row


# ---------------------------------------------------------------- AC-3.4.4 组合 C


def test_combination_3_unavailable_without_loan_is_hidden(app):
    """组合 C：unavailable + 无在借 → 学生列表与搜索均不出现；管理列表标「已停用」。"""
    item_id = _insert_item(app, NAME_C, "unavailable", category="book")
    anonymous = _client(app)
    student = _client(app, STUDENT_A)

    assert NAME_C not in _page(anonymous)
    assert NAME_C not in _page(anonymous, query={"q": NAME_C})
    assert NAME_C not in _page(student)
    assert NAME_C not in _page(student, query={"q": NAME_C})

    my_loans = _page(student, "/my-loans")
    assert NAME_C not in my_loans
    assert "当前没有在借物品" in my_loans

    cells, row_html = row_of(_page(_client(app, ADMIN), "/admin/items"), NAME_C)
    assert cells[2] == "已停用"
    assert cells[3] == "—"                             # 无借阅事实 → 应还日期占位
    assert cells[4] == "—"
    assert f"/admin/items/{item_id}/available" in row_html
    assert f"/admin/items/{item_id}/unavailable" not in row_html


# ---------------------------------------------------------------- AC-3.4.4 组合 D


def test_combination_4_unavailable_with_loan_hidden_but_returnable(app):
    """组合 D：unavailable + 在借 → 学生端不展示，但借阅者仍能看到并归还。

    展示优先级恒为 `unavailable > borrowed > available`：管理列表对这件物品
    必须标「已停用」（而不是「在借」），同时仍然给出在借人——两个事实并存。
    """
    item_id = _insert_item(app, NAME_D, "unavailable")
    loan_id = _insert_loan(app, item_id, user_pk=2)
    anonymous = _client(app)
    borrower = _client(app, STUDENT_B)
    other = _client(app, STUDENT_A)

    # 1) 学生端：停用优先，即使正在被别人借也不出现（AC-3.4.4 明文要求）
    assert NAME_D not in _page(anonymous)
    assert NAME_D not in _page(anonymous, query={"q": NAME_D})
    assert NAME_D not in _page(other)

    # 2) 借阅者仍能在 /my-loans 看到这条记录（D-005 用例 A 的渲染面）
    my_cells, my_row = row_of(_page(borrower, "/my-loans"), NAME_D)
    _assert_loan_state(my_cells[3])
    assert f"/return/{loan_id}" in my_row

    # 3) 管理列表：优先级 unavailable > borrowed
    admin_cells, admin_row = row_of(_page(_client(app, ADMIN), "/admin/items"), NAME_D)
    assert admin_cells[2] == "已停用"
    assert admin_cells[4] == "陈默"                     # 在借人仍如实显示
    assert "在借" not in admin_cells[2]
    assert f"/admin/items/{item_id}/available" in admin_row

    # 4) 归还照常成功，且物品保持停用（D-005 用例 A）
    assert borrower.post(f"/return/{loan_id}").status_code == 302
    assert _item_status(app, item_id) == "unavailable"
    my_loans = _page(borrower, "/my-loans")
    assert NAME_D not in my_loans
    assert "当前没有在借物品" in my_loans


# ---------------------------------------------------------------- AC-3.4.4 矩阵


def test_four_combinations_cross_rendered_in_one_state(app):
    """四种组合并存：两个列表一次渲染全部交叉核对（矩阵用例）。"""
    item_a = _insert_item(app, NAME_A, "available")
    item_b = _insert_item(app, NAME_B, "available")
    item_c = _insert_item(app, NAME_C, "unavailable")
    item_d = _insert_item(app, NAME_D, "unavailable")
    _insert_loan(app, item_b, user_pk=1)
    _insert_loan(app, item_d, user_pk=2)

    anonymous = _client(app)
    student_a = _client(app, STUDENT_A)
    student_b = _client(app, STUDENT_B)
    admin = _client(app, ADMIN)

    # 1) 学生列表：匿名与登录态给出一致的展示态与可见性
    student_states = state_map(_page(student_a))
    anonymous_states = state_map(_page(anonymous))
    assert anonymous_states == student_states
    assert student_states[NAME_A] == "可借"
    assert student_states[NAME_B] == "在借"
    assert NAME_C not in student_states
    assert NAME_D not in student_states

    # 2) 搜索结果：停用的两种组合即使被点名搜索也 0 命中
    searched = state_map(_page(anonymous, query={"q": "四态"}))
    assert set(searched) == {NAME_A, NAME_B}
    assert searched[NAME_A] == "可借"
    assert searched[NAME_B] == "在借"

    # 3) 我的借阅：每个借阅者只看到自己那条；停用不改变可见性
    my_a = state_map(_page(student_a, "/my-loans"), STATE_COLUMN_MY_LOANS)
    assert set(my_a) == {NAME_B}
    _assert_loan_state(my_a[NAME_B])
    my_b = state_map(_page(student_b, "/my-loans"), STATE_COLUMN_MY_LOANS)
    assert set(my_b) == {NAME_D}
    _assert_loan_state(my_b[NAME_D])

    # 4) 管理列表：四种组合全部可见，且优先级 unavailable > borrowed > available
    admin_states = state_map(_page(admin, "/admin/items"))
    assert admin_states[NAME_A] == "可借"
    assert admin_states[NAME_B] == "在借"
    assert admin_states[NAME_C] == "已停用"
    assert admin_states[NAME_D] == "已停用"

    # 5) 交叉比对：三张表的展示态与数据库事实逐条对齐（NFR-1.4 的静态面）
    truth = _sql_truth(app)
    assert set(admin_states) == set(truth)              # 管理列表覆盖全量、每件一行
    visible_expected = {name for name, (status, _n) in truth.items()
                        if status != "unavailable"}
    assert set(student_states) == visible_expected
    for name, (status, active) in truth.items():
        expected = ("已停用" if status == "unavailable"
                    else "在借" if active else "可借")
        assert admin_states[name] == expected, (name, status, active)
        if status == "unavailable":
            assert name not in student_states
        else:
            assert student_states[name] == ("在借" if active else "可借")

    # 6) 反向核对：列表里的每一行都能在库里找到对应物品（没有幽灵行）
    for name in student_states:
        assert name in truth, name
    # 四件被测物品都还在（本用例只读，不改状态）
    assert {item_a, item_b, item_c, item_d} <= {
        row["id"] for row in _all_item_ids(app)
    }


def _all_item_ids(app):
    with app.app_context():
        rows = db_module.get_db().execute("SELECT id FROM items").fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------- AC-3.4.6 结构


def test_ac_3_4_6_derivation_is_implemented_only_once():
    """AR-5/PC-8：`list_items_with_state` 是全项目唯一的「物品 + 在借」派生实现。"""
    definitions = []
    derivations = []
    for subdir in ("services", "routes"):
        for path in sorted((SOURCE_ROOT / subdir).glob("*.py")):
            text = _strip_docstrings(path.read_text(encoding="utf-8"))
            if "def list_items_with_state(" in text:
                definitions.append(f"{subdir}/{path.name}")
            for _match in re.finditer(r"LEFT\s+JOIN\s+loans", text, re.I):
                derivations.append(f"{subdir}/{path.name}")
    assert definitions == ["services/items.py"]
    # 「物品联 loans 未归还记录」的派生 SQL 只此一处，别处不得再写第二份
    assert derivations == ["services/items.py"]

    # 除唯一实现外，services/ 里不得出现 'borrowed' 字面量（存储态只有两值）
    for path in sorted((SOURCE_ROOT / "services").glob("*.py")):
        if path.name == "items.py":
            continue
        text = _strip_docstrings(path.read_text(encoding="utf-8"))
        assert "'borrowed'" not in text, f"{path.name} 私自构造了 borrowed 展示态"

    # 模板只渲染 display_state，不自己算在借（更不能读 loans 表）
    for name in ("items.html", "admin_items.html", "my_loans.html"):
        template = (SOURCE_ROOT / "templates" / name).read_text(encoding="utf-8")
        assert "returned_at" not in template, name
        assert "LEFT JOIN" not in template.upper(), name


def test_ac_3_4_6_every_list_calls_the_single_derivation(app, monkeypatch):
    """学生列表、搜索结果、管理列表三条路径都调用同一个函数（行为侧证据）。"""
    calls = []
    real_derivation = items_service.list_items_with_state

    def spy(*args, **kwargs):
        calls.append((args, dict(kwargs)))
        return real_derivation(*args, **kwargs)

    monkeypatch.setattr(items_route, "list_items_with_state", spy)
    monkeypatch.setattr(admin_route, "list_items_with_state", spy)

    anonymous = _client(app)
    assert anonymous.get("/items").status_code == 200
    assert anonymous.get("/items", query_string={"q": "算法"}).status_code == 200
    assert _client(app, ADMIN).get("/admin/items").status_code == 200

    assert calls == [
        ((), {"query": None}),
        ((), {"query": "算法"}),
        ((), {"include_unavailable": True}),
    ]


def test_row_probe_rejects_duplicate_rows():
    """脚手架自检：同一物品渲染两次必须当场失败（LEFT JOIN 翻倍的现场）。"""
    duplicated = (
        "<table><tbody>"
        "<tr><td>算法图解</td><td>图书</td><td>可借</td></tr>"
        "<tr><td>算法图解</td><td>图书</td><td>在借</td></tr>"
        "</tbody></table>"
    )
    try:
        rows_by_name(duplicated)
    except AssertionError as exc:
        assert "算法图解" in str(exc)
    else:  # pragma: no cover - 走到这里说明探针失去了唯一性断言
        raise AssertionError("页面探针未拦住重复行")
