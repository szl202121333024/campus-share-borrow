---
title: 'Story 1.3：物品列表与关键字搜索'
type: 'feature'
created: '2026-11-09'
status: 'draft'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'e99d0a6'
context:
  - '{project-root}/_bmad-output/project-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 物品列表和搜索功能已部分实现，但缺少访客/登录用户的差异化展示（匿名不显示借阅人姓名，登录用户显示），以及只读无副作用和性能测试。

**Approach:** 修改模板根据 `current_user` 条件渲染借阅人姓名列；补充 AC-1.3.6/1.3.7/1.3.9/1.3.10 的测试覆盖。

## Boundaries & Constraints

**Always:**
- 状态派生查询唯一真相：`list_items_with_state(...)`（PC-8、AR-5），不得另写第二份 SQL
- 搜索关键字 LIKE 转义：`%` 和 `_` 按字面量匹配（AC-1.3.3）
- 排序：先 book 后 equipment，组内按名称升序（AC-1.3.1）
- 响应头 `Cache-Control: no-store`（AC-1.3.8）
- 空状态文案「没有找到相关物品」（AC-1.3.5）
- 匿名请求不显示借阅人姓名，登录用户显示（AC-1.3.6）
- 响应体不出现任何学号字符串（AC-1.3.7）

**Never:** 不引入库存计数列；不修改 `items.status` 存储值；不写第二份物品查询 SQL

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| 匿名列表 | 未登录 GET /items | 200，6 件非停用物品，先 book 后 equipment，无借阅人姓名 | N/A |
| 登录列表 | 已登录 GET /items | 200，同上但显示借阅人姓名 | N/A |
| 关键字搜索 | GET /items?q=胶枪 | 200，仅匹配物品 | N/A |
| 通配符转义 | GET /items?q=% | 200，按字面量匹配（不返回全部） | N/A |
| 空搜索 | GET /items?q= | 200，等同于无搜索 | N/A |
| 无匹配 | GET /items?q=不存在 | 200，空状态文案 | N/A |
| 学号泄露 | 任意列表响应 | 响应体不含任何学号 | N/A |

</frozen-after-approval>

## Code Map

- `services/items.py` — 已有 `list_items_with_state(query=None)`，唯一派生查询，无需修改
- `routes/items.py` — 已有 `/items` 路由，`Cache-Control: no-store` 已设置，无需修改
- `templates/items.html` — 需修改：根据 `current_user` 条件渲染借阅人姓名列
- `tests/test_items.py` — 新增：覆盖 AC-1.3.1~1.3.10

## Tasks & Acceptance

**Execution:**
- [ ] `templates/items.html` — 根据 `current_user` 条件渲染借阅人姓名列
- [ ] `tests/test_items.py` — 覆盖 AC-1.3.1~1.3.10（列表排序、搜索转义、空状态、访客/登录差异化、学号不泄露、只读无副作用、性能）

**Acceptance Criteria:**
- Given 库中有 book 与 equipment 两类共 6 件非停用物品，when 匿名 GET /items，then 200，先 book 后 equipment，组内按名称升序，不出现 unavailable 物品
- Given 列表中有一件名称含「胶枪」的物品，when GET /items?q=胶枪，then 200，结果仅含匹配物品，匹配忽略英文大小写与首尾空白
- Given 搜索框，when 输入单个 % 或 _，then 按普通字符匹配，不返回全部物品
- Given GET /items 且 q 缺失或纯空白，when 渲染，then 等同于无搜索，返回全部非停用物品
- Given 关键字无任何匹配，when GET /items?q=不存在的名字，then 200，渲染空状态文案「没有找到相关物品」
- Given 一件物品存在未归还借阅记录，when 渲染列表，then 该条目标记为「在借」并展示应还日期；匿名请求不出现借阅人姓名；已登录用户出现借阅人姓名
- Given 任意列表或搜索响应，when 检索响应体，then 不出现任何学号字符串
- Given 任意列表或搜索响应，when 检查响应头，then 含 Cache-Control: no-store
- Given 借阅记录行数与 items.status 的初始快照，when 连续执行两次相同搜索请求，then 两次响应体一致，loans 行数与 items.status 与快照逐字段一致
- Given 50 条物品规模的种子数据，when 对 GET /items 与 GET /items?q= 各发 20 次请求，then 服务端处理耗时 p95 < 200ms

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Design Notes

## Verification

**Commands:**
- `python -m pytest tests/test_items.py -v` — Story 1.3 全部用例通过
- `python -m pytest -q` — 全量测试通过（Story 1.1 + 1.2 + 1.3）
