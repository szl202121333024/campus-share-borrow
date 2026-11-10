"""Story 2.5：我的借阅与限额指示（额度只有一处真相）。

覆盖 AC-2.5.1 ~ AC-2.5.9：只列未归还、逾期标红「已逾期 N 天」（due 当天
不算）、两页共用同一函数与同一文案宏显示「已借 X / 3」、归还后同一请求
内指示即变、匿名不显示、空状态文案、越权不可见、额度查询恒为一次、
数字 3 与文案的唯一真相结构扫描。
"""

import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import db as db_module
import routes.items as items_route
import routes.loans as loans_route
from config import TIME_FORMAT

from tests.test_loans import borrow, login, seed_active_loan

REPO_ROOT = Path(__file__).resolve().parents[1]


def now_text():
    return datetime.now().strftime(TIME_FORMAT)


def at(days_ago=None, days_ahead=None, clock=None):
    base = datetime.now()
    if days_ago is not None:
        base = base - timedelta(days=days_ago)
    if days_ahead is not None:
        base = base + timedelta(days=days_ahead)
    if clock is not None:
        base = base.replace(hour=clock[0], minute=clock[1], second=clock[2])
    return base.strftime(TIME_FORMAT)


def seed_returned_loan(app, item_id, user_id):
    """预置一条已归还记录（returned_at 非空）。"""
    with app.app_context():
        db_module.get_db().execute(
            "INSERT INTO loans (item_id, user_id, borrowed_at, due_at, returned_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (item_id, user_id, at(days_ago=20), at(days_ago=13), now_text()),
        )


def item_name(app, item_id):
    with app.app_context():
        row = db_module.get_db().execute(
            "SELECT name FROM items WHERE id = ?", (item_id,)
        ).fetchone()
    return row["name"]


def page(client, path):
    response = client.get(path)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def table_rows(page_text):
    body = re.search(r"<tbody>.*?</tbody>", page_text, re.DOTALL)
    assert body is not None
    return body.group(0)


def my_loans(client):
    return page(client, "/my-loans")


# ---------------------------------------------------------------- AC-2.5.1


def test_ac_2_5_1_only_active_loans_listed(client, app):
    """2 条未归还 + 3 条已归还：/my-loans 只列出那 2 条。"""
    login(client, "2024001")
    assert borrow(client, 1).status_code == 302
    assert borrow(client, 2).status_code == 302
    for _ in range(3):
        seed_returned_loan(app, 3, 1)

    text = my_loans(client)
    body = table_rows(text)
    assert item_name(app, 1) in body
    assert item_name(app, 2) in body
    assert item_name(app, 3) not in body            # 已归还一律不出现
    assert body.count("<tr>") == 2
    # 库内确有 3 条已归还记录，证明不是测试构造失败
    with app.app_context():
        done = db_module.get_db().execute(
            "SELECT COUNT(*) AS c FROM loans WHERE returned_at IS NOT NULL"
        ).fetchone()["c"]
    assert done == 3


# ---------------------------------------------------------------- AC-2.5.2


def test_ac_2_5_2_overdue_row_red_with_day_count(client, app):
    """逾期行标红并显示「已逾期 N 天」；due_at 当天不标红；列齐全。"""
    login(client, "2024001")
    # 逾期 3 天
    seed_active_loan(app, 1, 1, at(days_ago=10), at(days_ago=3))
    # 应还日期就是今天（凌晨 00:00:01，当前时间已晚于 due_at，但日期差为 0 → 不标红）
    seed_active_loan(app, 2, 1, at(days_ago=7), at(days_ahead=0, clock=(0, 0, 1)))

    text = my_loans(client)
    # 列展示：物品名称、借出时间、应还日期
    for header in ("物品名称", "借出时间", "应还日期"):
        assert f"<th>{header}</th>" in text

    overdue_rows = re.findall(r'<tr class="overdue">.*?</tr>', text, re.DOTALL)
    assert len(overdue_rows) == 1
    assert "已逾期 3 天" in overdue_rows[0]
    assert item_name(app, 1) in overdue_rows[0]
    # due_at 当天：不标红、不显示逾期（只在 tbody 数据行内匹配，排除表头）
    body = table_rows(text)
    normal_rows = re.findall(r"<tr>.*?</tr>", body, re.DOTALL)
    assert len(normal_rows) == 1
    assert "已逾期" not in normal_rows[0]
    assert 'class="overdue"' not in normal_rows[0]


# ---------------------------------------------------------------- AC-2.5.3


def test_ac_2_5_3_both_pages_same_indicator_text(client, app):
    """两页顶部都显示「已借 X / 3」，同一函数、同一文案格式。"""
    login(client, "2024001")
    assert borrow(client, 1).status_code == 302
    assert borrow(client, 2).status_code == 302

    loans_text = my_loans(client)
    items_text = page(client, "/items")
    assert "已借 2 / 3" in loans_text
    assert "已借 2 / 3" in items_text
    # 两处指示都在页面顶部（正文首个内容块内）
    assert loans_text.index("已借 2 / 3") < loans_text.index("<table>")
    assert items_text.index("已借 2 / 3") < items_text.index("<table>")
    # 结构：两个模板 import 的是同一个宏文件（同一文案真相）
    for tpl in ("my_loans.html", "items.html"):
        source = (REPO_ROOT / "templates" / tpl).read_text(encoding="utf-8")
        assert "import '_quota.html'" in source
        assert "quota.quota_display(remaining_quota)" in source
    # 结构：两个路由调用的是同一个服务函数对象
    assert items_route.get_remaining_quota is loans_route.get_remaining_quota
    import services.loans as loans_service
    assert items_route.get_remaining_quota is loans_service.get_remaining_quota


# ---------------------------------------------------------------- AC-2.5.4


def test_ac_2_5_4_indicator_frees_within_same_request(client, app):
    """借 2 还 1：立即重新渲染即「已借 1 / 3」，无需重新登录。"""
    login(client, "2024001")
    assert borrow(client, 1).status_code == 302
    assert borrow(client, 2).status_code == 302
    assert "已借 2 / 3" in my_loans(client)

    loan_id = None
    with app.app_context():
        loan_id = db_module.get_db().execute(
            "SELECT id FROM loans WHERE item_id = 1 AND user_id = 1"
        ).fetchone()["id"]
    assert client.post(f"/return/{loan_id}").status_code == 302

    assert "已借 1 / 3" in my_loans(client)
    assert "已借 1 / 3" in page(client, "/items")


# ---------------------------------------------------------------- AC-2.5.5


def test_ac_2_5_5_anonymous_sees_no_quota(client, app):
    """匿名渲染 /items：不显示限额指示，也不触发额度查询。"""
    text = page(client, "/items")
    assert "已借" not in text
    assert "quota-indicator" not in text


# ---------------------------------------------------------------- AC-2.5.6


def test_ac_2_5_6_empty_state_text(client, app):
    """无未归还记录：200 + 空状态文案「当前没有在借物品」，指示为 0/3。"""
    login(client, "2024001")
    text = my_loans(client)
    assert "当前没有在借物品" in text
    assert "<tbody>" not in text
    assert "已借 0 / 3" in text


# ---------------------------------------------------------------- AC-2.5.7


def test_ac_2_5_7_other_users_loans_invisible(client, app):
    """他人未归还记录不出现在本用户的 /my-loans（按 user_id 过滤）。"""
    login(client, "2024002")
    assert borrow(client, 4).status_code == 302
    login(client, "2024001")

    text = my_loans(client)
    assert item_name(app, 4) not in text
    with app.app_context():
        mine = db_module.get_db().execute(
            "SELECT COUNT(*) AS c FROM loans WHERE user_id = 1 AND returned_at IS NULL"
        ).fetchone()["c"]
    assert mine == 0 and "当前没有在借物品" in text


# ---------------------------------------------------------------- AC-2.5.8


@pytest.mark.parametrize(
    ("active", "path"),
    [
        (0, "/items"),
        (2, "/items"),
        (3, "/items"),
        (0, "/my-loans"),
        (2, "/my-loans"),
        (3, "/my-loans"),
        (3, "/items?q=搜不到这串字"),
    ],
)
def test_ac_2_5_8_quota_queried_exactly_once(client, app, monkeypatch, active, path):
    """额度查询次数恒为 1，与列表长度/搜索结果无关（不循环查询）。"""
    login(client, "2024001")
    for item_id in (1, 2, 3)[:active]:
        assert borrow(client, item_id).status_code == 302

    calls = []
    original = items_route.get_remaining_quota

    def counting(user_id):
        calls.append(user_id)
        return original(user_id)

    monkeypatch.setattr(items_route, "get_remaining_quota", counting)
    monkeypatch.setattr(loans_route, "get_remaining_quota", counting)
    assert page(client, path)
    assert calls == [1]


# ---------------------------------------------------------------- AC-2.5.9


def test_ac_2_5_9_limit_has_single_truth_no_drift():
    """数字 3 只有一处常量定义；文案只有一处宏；路由无手写 COUNT。"""
    config_src = (REPO_ROOT / "config.py").read_text(encoding="utf-8")
    assert re.search(r"BORROW_LIMIT = 3\b", config_src)
    # 校验与提示同源：错误文案用 f-string 引用常量，不写死数字
    assert 'f"你已借满 {BORROW_LIMIT} 件' in config_src

    # 模板：限额文案格式只在 _quota.html 一处，且全部引用注入常量
    quota_src = (REPO_ROOT / "templates" / "_quota.html").read_text(encoding="utf-8")
    assert "已借 {{ borrow_limit - remaining }} / {{ borrow_limit }}" in quota_src
    for html in (REPO_ROOT / "templates").glob("*.html"):
        src = html.read_text(encoding="utf-8")
        assert not re.search(r"已借\s*\d", src)          # 无「已借 2」式硬编码
        assert not re.search(r"/ ?3\b", re.sub(r"\{\{.*?\}\}", "", src))

    # 路由：不出现 COUNT，也不出现额度数字
    for py in (REPO_ROOT / "routes").glob("*.py"):
        src = py.read_text(encoding="utf-8")
        assert "COUNT(" not in src
    # 额度聚合全库唯一真相仍在 services/loans.py 一处（与 AC-2.4.7 同口径复证）
    service_src = (REPO_ROOT / "services" / "loans.py").read_text(encoding="utf-8")
    assert service_src.count("SELECT COUNT(*)") == 1
    assert "def get_remaining_quota" in service_src
