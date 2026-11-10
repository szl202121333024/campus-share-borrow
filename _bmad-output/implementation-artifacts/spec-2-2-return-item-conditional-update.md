---
title: 'Story 2.2：归还物品（条件 UPDATE、停用物品保持停用）'
type: 'feature'
created: '2026-11-10'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '1e2fb38'
context:
  - _bmad-output/project-context.md
  - _bmad-output/planning-artifacts/epics.md#story-22
  - decision-log.md（D-005、D-011、D-014、D-020）
  - architecture/ADR-002（§2.3 归还路径）
---

# Story 2.2：归还物品

## Summary

借阅者对本人未归还记录 `POST /return/<loan_id>`，服务端以**一条条件 UPDATE**
写 `returned_at` 并用 `rowcount` 判成败（D-014）；`rowcount == 0` 时仅补一次
`SELECT` 区分 409 `ALREADY_RETURNED`（本人已归还）与 404 `RESOURCE_NOT_FOUND`
（他人记录 / 不存在 id，两者响应逐字节一致，D-011）。归还全程不写 `items` 表：
停用物品归还后保持 `unavailable`（D-005 用例 A），学生列表展示态由既有派生
查询（`services/items.py`）自动回到「可借」。`/my-loans` 升级为本故事的最小
可用版：渲染本人全部借还记录、逾期标红、归还入口。

## 实现落点

| 文件 | 变更 |
| --- | --- |
| `services/loans.py` | 新增 `return_loan()`：`BEGIN IMMEDIATE` 事务内条件 `UPDATE loans SET returned_at = ? WHERE id = ? AND user_id = ? AND returned_at IS NULL` + `cur.rowcount == 1` 判定；rowcount 0 → 一次 `SELECT returned_at FROM loans WHERE id = ? AND user_id = ?` 分流 409/404。新增 `list_user_loans()`：单条 SQL 派生 `is_overdue`，归还后自动归 0 |
| `routes/loans.py` | 新增 `POST /return/<int:loan_id>`：调服务 → flash「已归还，借阅额度已释放」→ 302 `/my-loans` + `Cache-Control: no-store`（PC-9 PRG）；`GET /my-loans` 渲染 `list_user_loans()` 结果 |
| `templates/my_loans.html` | 占位页 → 最小可用版：借还记录表、`class="overdue"` 标红、未归还行「归还」按钮（PC-1：模板零业务判断，逾期只在 SQL 派生一次） |
| `static/style.css` | 补 `.overdue td` 标红样式 |
| `tests/test_returns.py` | 新建，12 个用例：AC-2.2.1~2.2.11 逐条 + 非数字 loan_id 边界 |

## 规约自检（project-context 检查单）

- PC-1 路由只收参数/调服务/映射异常 ✔
- PC-4 写路径经 `write_transaction()`（BEGIN IMMEDIATE），`BEGIN DEFERRED` 全库 0 命中 ✔
- PC-6/D-014/D-020 归还只写 `loans`；`services/loans.py` 全文检索 `UPDATE items` 0 命中（AC-2.2.10 有结构断言） ✔
- PC-9 409/404 真实状态码 + 错误码与文案同源（`config.ERROR_MESSAGES`） ✔
- PC-10 无角色分支；①未登录 302 由 `routes/auth.py` 统一守卫承担（`/return/` 前缀已在白名单，Story 1.2 预留） ✔
- PC-13 `test_returns.py` / `test_ac_2_2_*` 命名；并发用例真 barrier + 20 轮 ✔
- PC-14 `returned_at` 用 `now_text()` 服务端时间，格式同源 ✔

## 测试

- 单故事：`pytest tests/test_returns.py` → **12 passed**
- 全量回归：`pytest -q` → **92 passed**（借阅 15 + 归还 12 + 既有 65，零回归）

## 已知边界（不阻塞，登记 deferred-work）

1. AC-2.2.9 用 `test_client` + barrier 做进程内双会话并发；NFR-1.3 的正式
   硬核验收（独立进程 / 独立连接直压）仍按阶段 2 裁决留在 Story 2.3 脚手架，
   本故事的 20 轮冒烟不替代该验收。
2. 停用状态用直接 SQL 构造（本故事技术要点明确授权）；管理员停用入口属
   Story 3.3。
3. `/my-loans` 为最小可用版（归还入口 + 逾期标红）；额度展示与完整版在
   Story 2.5 收口。
