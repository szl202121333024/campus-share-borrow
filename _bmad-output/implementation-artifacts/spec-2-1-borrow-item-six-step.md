---
title: 'Story 2.1：借阅物品（六步判定与应还日期）'
type: 'feature'
created: '2026-11-09'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '8655094'
context:
  - '{project-root}/_bmad-output/project-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 列表页目前只有浏览与搜索，学生无法把物品借到手；失败如果统一返回笼统提示，用户无法区分「已被别人借走」「额度已满」「物品停用」，双击还会产生重复记录或互相矛盾的错误码。

**Approach:** 服务层单函数 `services/loans.py::borrow_item()` 按 PRD FR-3 的六步固定顺序判定（PC-5）：①未登录 302（复用 Story 1.2 统一守卫）→ ②不存在 404 → ③停用 409 → ④已持有 409 → ⑤限额 409 → ⑥唯一索引兜底 409（与 ④ 逐字一致，D-016）。整个写路径包在 `BEGIN IMMEDIATE`（`db.write_transaction()`，AC-2.1.10）；②③ 共用一条 `SELECT id, status FROM items`，④⑤ 共用一条聚合查询（D-008、AC-2.1.9）。路由只收参数、调服务、PRG 302（PC-1、PC-9）。

## Boundaries & Constraints

**Always:**
- 六步顺序不可重排（PRD FR-3、D-006、D-008、PC-5）；同时命中多条判定时取序号最小者（AC-2.1.8 四组合表）
- ②③ 一次查询、④⑤ 一次聚合查询；单次借阅对 `loans` 的读取恰好 1 次（AC-2.1.9）
- 写事务只用 `BEGIN IMMEDIATE`，COUNT 与 INSERT 同事务（AR-1、D-009、PC-4、AC-2.1.10）
- `IntegrityError` 精确捕获（只捕这一种），映射结果与 ④ 的状态码、错误码、文案逐字一致（D-016、AC-2.1.6）
- 失败返回真实 4xx + `config.ERROR_MESSAGES` 同源中文（PC-9）；成功走 POST + 302（PRG）
- `due_at = borrowed_at + 7 天`，按天为整数、时分秒不漂移（PC-14、AC-2.1.1）
- 逾期记录计入额度（returned_at IS NULL 即计入），但逾期本身不构成拦截（AC-2.1.12、FR-5）
- 借阅与额度逻辑不出现任何以角色为条件的分支（PC-10、D-012）
- 失败请求前后 `loans` 行数与 `items` 全字段逐字段不变（NFR-1.5、AC-2.1.11）

**Never:** 不引入库存计数列；不写 `UPDATE items`（借阅只读 items、只写 loans）；不用 `BEGIN DEFERRED`；不在 routes/ 写 SQL；不新建第二份额度 SQL（Story 2.5 才会定义 `get_remaining_quota()`，本故事不得提前创建）

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| 正常借阅 | 登录、额度未满、available | 302 → /items，flash「借阅成功，应还日期 YYYY-MM-DD」，loans +1 | N/A |
| 借阅后列表 | 立即 GET /items | 该物品「在借」+ 应还日期，no-store | N/A |
| 他人已借走 | 存在未归还记录（他人） | 409 ALREADY_BORROWED「该物品已被借出」，行数不变 | ④ |
| 物品不存在 | item_id 无此行 | 404 RESOURCE_NOT_FOUND | ② |
| 物品停用 | status='unavailable' | 409 ITEM_UNAVAILABLE，不产生记录 | ③ |
| 双击第二次 | 本人已持有 | 409 ALREADY_BORROWED，与 ⑥ 路径逐字一致 | ④/⑥ |
| 并发竞态 | 两请求同时过 ④ | 恰一成功；输者 IntegrityError → 同 ④ 响应 | ⑥ |
| 额度已满 | 在借 3 件（逾期计入） | 409 LIMIT_EXCEEDED「你已借满 3 件，请先归还」 | ⑤ |
| 未登录+不存在 | 无会话 POST | 302 → /login?next=/borrow | ① |
| 停用+满额 | 同时命中 ③⑤ | 409 ITEM_UNAVAILABLE（取序号最小） | ③ |
| 已持有+满额 | 同时命中 ④⑤ | 409 ALREADY_BORROWED（取序号最小） | ④ |
| 不存在+满额 | 同时命中 ②⑤ | 404 RESOURCE_NOT_FOUND（取序号最小） | ② |
| 非数字 item_id | "abc" | 400 INVALID_INPUT，零副作用 | 路由入参校验 |

</frozen-after-approval>

## Code Map

- `db.py` — 修改：新增 `write_transaction()` 写事务原语（全项目共享，归还与管理写路径复用）
- `services/loans.py` — 新建：`borrow_item(user_id, item_id)` 六步判定 + `_loan_counts()` 唯一聚合查询
- `routes/loans.py` — 修改：新增 `POST /borrow`（入参校验 → 服务 → flash + 302）
- `templates/items.html` — 修改：登录用户可见「借阅人」「操作」列，available 行渲染借阅表单（纯展示判断，PC-1）
- `tests/test_loans.py` — 新建：AC-2.1.1 ~ AC-2.1.12 + 入参校验 + 双客户端并发冒烟（20 轮）

## Tasks & Acceptance

**Execution:**
- [x] `db.py::write_transaction()` — BEGIN IMMEDIATE / 异常必 ROLLBACK / 成功 COMMIT
- [x] `services/loans.py::borrow_item()` — 六步判定、单查询、单事务、IntegrityError 映射
- [x] `routes/loans.py::borrow()` — item_id 入参校验（400 INVALID_INPUT）、PRG 302 + flash
- [x] `templates/items.html` — 借阅人列拆分 + 借阅表单（仅登录渲染）
- [x] `tests/test_loans.py` — 覆盖 AC-2.1.1~12 全部 12 条 + 边界

**Acceptance Criteria:** 见 epics.md Story 2.1（AC-2.1.1 ~ AC-2.1.12），逐条对应 tests/test_loans.py 同名用例。

## Implementation Notes

- ⑥ 的触发路径在单线程下通过「预置他人记录 + monkeypatch 聚合计数归零」复现，使 INSERT 真实撞上 `ux_loans_active_item`，验证异常映射与 ④ 逐字一致（不放宽为伪造异常）。
- 并发冒烟：两个独立登录会话的 test_client + `threading.Barrier` 同时 POST 同一物品，20 轮，每轮断言恰一个 302、一个 409、在借记录恰 1 条。正式 NFR-1.1 验收仍属 Story 2.3，本冒烟仅验证事务与索引机制可用。
- 组合 1（未登录+不存在）由 `routes/auth.py` 守卫在进入路由前 302，`/borrow` 路径已在 Story 1.2 预留，本故事零改动。
- `flash` 文案含应还日期仅到日（YYYY-MM-DD），与 AC-2.1.1 措辞一致。

## Spec Change Log

（无——按 epics.md 原文实现，未修改任何 AC）

## Review Triage Log

（待评审）

## Design Notes

- `write_transaction()` 放在 `db.py` 而非各服务自行 BEGIN，保证 PC-4 审计只需检索一处原语。
- `_loan_counts` 用一条 `SUM(CASE WHEN...)` 同时得出 ④⑤ 两个计数，满足「单次借阅对 loans 读取恰好 1 次」（AC-2.1.9）。
- `except sqlite3.IntegrityError` 置于事务上下文之外：ROLLBACK 已先于映射执行，失败零残留（AC-2.1.11）。

## Verification

**Commands:**
- `python -m pytest tests/test_loans.py -v` — 实测 15 passed（AC-2.1.1~2.1.12 + 入参校验 + 20 轮并发冒烟）
- `python -m pytest -q` — 实测 80 passed（bootstrap + auth + items + loans，无回归）
