"""Story 2.2：归还物品——条件 UPDATE、停用保持停用（AC-2.2.1 ~ AC-2.2.11）。"""

import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import db as db_module
from config import TIME_FORMAT

from tests.test_loans import active_loans, borrow, login, seed_active_loan

REPO_ROOT = Path(__file__).resolve().parents[1]


def return_loan(client, loan_id):
    return client.post(f"/return/{loan_id}")


def get_loan_row(app, loan_id):
    with app.app_context():
        return db_module.get_db().execute(
            "SELECT * FROM loans WHERE id = ?", (loan_id,)
        ).fetchone()


def loan_returned_at(app, loan_id):
    row = get_loan_row(app, loan_id)
    return row["returned_at"] if row else None


def table_body(page_text):
    """只取 <tbody> 区段，避免页头当前用户姓名干扰借阅人列的断言。"""
    match = re.search(r"<tbody>.*?</tbody>", page_text, re.DOTALL)
    assert match is not None
    return match.group(0)


def loan_row_for_item(app, item_id):
    with app.app_context():
        return db_module.get_db().execute(
            "SELECT * FROM loans WHERE item_id = ?", (item_id,)
        ).fetchone()


def item_status(app, item_id):
    with app.app_context():
        row = db_module.get_db().execute(
            "SELECT status FROM items WHERE id = ?", (item_id,)
        ).fetchone()
    return row["status"] if row else None


# ---------------------------------------------------------------- 正常路径


def test_ac_2_2_1_return_writes_returned_at_and_redirects(client, app):
    """AC-2.2.1：本人未归还记录 POST /return → 302 /my-loans +「已归还」，
    returned_at 为服务端当前时间且落在请求前后窗口内。"""
    login(client, "2024001")
    assert borrow(client, 1).status_code == 302
    loan = get_loan_row(app, 1)
    before = datetime.now()
    response = return_loan(client, loan["id"])
    after = datetime.now()
    assert response.status_code == 302
    assert "/my-loans" in response.headers["Location"]

    page = client.get(response.headers["Location"], follow_redirects=True)
    assert "已归还" in page.get_data(as_text=True)

    stored = loan_returned_at(app, loan["id"])
    assert stored is not None
    moment = datetime.strptime(stored, TIME_FORMAT)
    # 服务端秒级文本必须落在请求前后窗口内（容忍秒取整 ±1s）
    assert before - timedelta(seconds=1) <= moment <= after + timedelta(seconds=1)


def test_ac_2_2_2_available_state_derives_without_items_write(client, app):
    """AC-2.2.2：归还后 /items 该物品恢复可借，借阅人与应还日期消失；
    该变化由派生查询给出，归还全程 items 行逐字节不变（D-005 佐证）。"""
    login(client, "2024001")
    assert borrow(client, 1).status_code == 302

    with app.app_context():
        db = db_module.get_db()
        before = tuple(db.execute("SELECT * FROM items WHERE id = 1").fetchone())
    assert "林晓" in table_body(client.get("/items").get_data(as_text=True))

    loan = loan_row_for_item(app, 1)
    assert return_loan(client, loan["id"]).status_code == 302

    page = client.get("/items").get_data(as_text=True)
    assert "林晓" not in table_body(page)
    assert "可借" in page
    with app.app_context():
        db = db_module.get_db()
        after = tuple(db.execute("SELECT * FROM items WHERE id = 1").fetchone())
    assert after == before


def test_ac_2_2_3_disabled_item_stays_disabled_after_return(client, app):
    """AC-2.2.3（D-005 用例 A）：停用物品归还成功、returned_at 非空、
    status 保持 unavailable、且不出现在学生列表（本故事直接 SQL 构造停用）。"""
    login(client, "2024001")
    assert borrow(client, 2).status_code == 302
    with app.app_context():
        db_module.get_db().execute(
            "UPDATE items SET status = 'unavailable' WHERE id = 2"
        )

    loan = loan_row_for_item(app, 2)
    assert return_loan(client, loan["id"]).status_code == 302
    assert loan_returned_at(app, loan["id"]) is not None
    assert item_status(app, 2) == "unavailable"

    page = client.get("/items").get_data(as_text=True)
    assert "活着" not in page  # 停用物品已从学生列表消失


# ---------------------------------------------------------------- 逾期归还


def test_ac_2_2_4_overdue_return_ok_and_red_flag_gone(client, app):
    """AC-2.2.4：逾期记录（due_at 已过）仍可归还（302 +「已归还」）；
    归还后 /my-loans 不再标红、不再显示逾期。"""
    past_due = (datetime.now() - timedelta(days=2)).strftime(TIME_FORMAT)
    borrowed_at = (datetime.now() - timedelta(days=9)).strftime(TIME_FORMAT)
    seed_active_loan(app, 1, 1, borrowed_at, past_due)
    login(client, "2024001")

    page = client.get("/my-loans").get_data(as_text=True)
    assert 'class="overdue"' in page and "已逾期" in page

    assert return_loan(client, 1).status_code == 302
    page = client.get("/my-loans").get_data(as_text=True)
    assert 'class="overdue"' not in page
    assert "已逾期" not in page
    assert "已归还" in page


# ---------------------------------------------------------- 重复归还 / 归属


def test_ac_2_2_5_double_return_is_409_and_keeps_original_value(client, app):
    """AC-2.2.5：对已归还记录再次 POST → 409 + ALREADY_RETURNED +「该记录已归还」，
    returned_at 原值逐字节不变（条件 UPDATE 的 WHERE 挡住二次写入）。"""
    login(client, "2024001")
    assert borrow(client, 1).status_code == 302
    loan = get_loan_row(app, 1)
    assert return_loan(client, loan["id"]).status_code == 302

    first = loan_returned_at(app, loan["id"])
    response = return_loan(client, loan["id"])
    assert response.status_code == 409
    body = response.get_data(as_text=True)
    assert "ALREADY_RETURNED" in body and "该记录已归还" in body
    assert loan_returned_at(app, loan["id"]) == first


def test_ac_2_2_6_foreign_and_missing_loan_are_identical_404(client, app):
    """AC-2.2.6（D-011）：他人记录与不存在 id 均 404 RESOURCE_NOT_FOUND，
    且两个响应状态码、错误码、文案逐字节一致。"""
    login(client, "2024001")
    assert borrow(client, 1).status_code == 302          # 物品 1 → 用户 1
    login_other = client
    loan_of_user1 = get_loan_row(app, 1)

    # 换 2024002 登录（同一 client 重新登录即切换身份）
    login(client, "2024002")
    foreign = return_loan(client, loan_of_user1["id"])
    missing = return_loan(client, 99999)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.get_data(as_text=True) == missing.get_data(as_text=True)
    assert "RESOURCE_NOT_FOUND" in foreign.get_data(as_text=True)
    # 他人记录未被改动
    assert loan_returned_at(app, loan_of_user1["id"]) is None


def test_ac_2_2_7_anonymous_return_redirects_before_ownership(client, app):
    """AC-2.2.7：未登录 POST /return → 302 到 /login?next=/return/<id>（顺序 ①，
    先于归属判断——他人/不存在的 id 同样先被重定向，不会得到 404）。"""
    response = client.post("/return/1")
    assert response.status_code == 302
    location = response.headers["Location"]
    assert "/login" in location and "next=" in location and "/return/1" in location
    assert loan_returned_at(app, 1) is None


# ---------------------------------------------------------------- 额度释放


def test_ac_2_2_8_quota_released_within_same_request(client, app):
    """AC-2.2.8：借满 3 件后归还 1 件，立即再借新物品即 302 成功，
    不再出现 LIMIT_EXCEEDED（额度在同一请求内、随 returned_at 写入即释放）。"""
    login(client, "2024001")
    for item_id in (1, 2, 3):
        assert borrow(client, item_id).status_code == 302
    assert borrow(client, 4).status_code == 409          # 满额
    assert return_loan(client, 1).status_code == 302     # 归还 loan id 1
    response = borrow(client, 4)
    assert response.status_code == 302
    assert "LIMIT_EXCEEDED" not in response.get_data(as_text=True)
    assert active_loans(app) == 3


# ---------------------------------------------------------------- 并发归还


def test_ac_2_2_9_concurrent_return_one_success_one_conflict(client, app):
    """AC-2.2.9（NFR-1.3）：同一记录两会话并发 POST /return，
    状态码集合恰好 {302, 409}；returned_at 只写入一次且并发后不再变化；20 轮。"""
    login(client, "2024001")
    assert borrow(client, 1).status_code == 302
    loan_id = get_loan_row(app, 1)["id"]

    for round_no in range(1, 21):
        with app.app_context():
            db_module.get_db().execute(
                "UPDATE loans SET returned_at = NULL WHERE id = ?", (loan_id,)
            )
        barrier = threading.Barrier(2)
        results = {}
        errors = {}

        def attempt(tag):
            own_client = app.test_client()
            login(own_client, "2024001")
            try:
                barrier.wait()
                response = own_client.post(f"/return/{loan_id}")
                results[tag] = response.status_code
            except BaseException as exc:
                errors[tag] = repr(exc)

        threads = [threading.Thread(target=attempt, args=(tag,)) for tag in ("x", "y")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert errors == {}, (round_no, errors)
        assert sorted(results.values()) == [302, 409], (round_no, results)
        loser = [t for t, c in results.items() if c == 409][0]
        # 失败方是 409 ALREADY_RETURNED：用第三个会话重放一次即可拿到响应体核对
        check = app.test_client()
        login(check, "2024001")
        replay = check.post(f"/return/{loan_id}")
        assert replay.status_code == 409
        assert "ALREADY_RETURNED" in replay.get_data(as_text=True)
        # returned_at 只写一次且已稳定：间隔后再读逐字节一致
        stable_a = loan_returned_at(app, loan_id)
        assert stable_a is not None
        stable_b = loan_returned_at(app, loan_id)
        assert stable_a == stable_b, (round_no, results, loser)


# ---------------------------------------------------------------- 结构断言


def test_ac_2_2_10_return_path_has_no_items_update():
    """AC-2.2.10（D-014）：归还实现所在服务文件全文检索 UPDATE items 命中 0。"""
    source = (REPO_ROOT / "services" / "loans.py").read_text(encoding="utf-8")
    pattern = "UPDATE " + "items"
    assert pattern not in source
    assert re.search(pattern, source) is None


def test_ac_2_2_11_return_uses_conditional_update_with_rowcount():
    """AC-2.2.11：归还使用带 returned_at IS NULL 的条件 UPDATE，并以 rowcount
    判成败；rowcount == 0 后仅一次额外 SELECT 区分 409/404。"""
    source = (REPO_ROOT / "services" / "loans.py").read_text(encoding="utf-8")
    update_block = re.search(
        r'"UPDATE loans SET returned_at = \?"'
        r'\s*" WHERE id = \? AND user_id = \? AND returned_at IS NULL"',
        source,
    )
    assert update_block is not None
    after_update = source[update_block.end():]
    assert "cur.rowcount == 1" in after_update
    select_block = re.search(
        r'"SELECT returned_at FROM loans WHERE id = \? AND user_id = \?"', after_update
    )
    assert select_block is not None
    tail = after_update[select_block.start():]
    assert 'BizError(409, "ALREADY_RETURNED")' in tail
    assert 'BizError(404, "RESOURCE_NOT_FOUND")' in tail


def test_return_nonexistent_row_count_zero(client, app):
    """补充边界：loan_id 非数字 → 路由解析 404（Flask int 转换器），
    未登录场景下 AC-2.2.7 守卫先行重定向，不泄露记录存在性。"""
    login(client, "2024001")
    response = client.post("/return/abc")
    assert response.status_code == 404
    assert loan_returned_at(app, 1) is None
