---
title: 'Story 2.5：我的借阅与限额指示（额度只有一处真相）'
type: 'feature'
created: '2026-11-10'
status: 'done'
baseline_commit: 'eb694ec'
---

# Story 2.5：我的借阅与限额指示

## 目标与口径
- `GET /my-loans` 只列未归还记录；顶部显示「已借 X / 3」，与登录后的 `/items` 共用同一函数与同一文案格式（D-013）。
- 逾期行标红并显示「已逾期 N 天」，N 为当前日期与应还日期的日期差；due_at 当天不算逾期。
- 按用户指令：is_overdue 由 Python 服务层计算，模板只渲染红色与天数。

## 实现
- `services/loans.py::list_user_loans()` 重写为完整版：查询按 `user_id + returned_at IS NULL` 过滤，`is_overdue/overdue_days` 在 Python 层用 `datetime.strptime(...).date()` 日期差计算（模板与路由零换算）。
- 新增 `templates/_quota.html`：限额文案唯一宏 `quota_display(remaining)`，X = borrow_limit - remaining 的换算只在宏内做一次；两页 `{% import ... with context %}` 共用（不带 context 宏看不到注入常量，首跑 13 例失败即此因，已修）。
- `app.py`：context processor 注入 `borrow_limit = BORROW_LIMIT`（模板不写死数字，AC-2.5.9）。
- `routes/items.py`：登录态调用 `get_remaining_quota(user["id"])` 传入模板；匿名不调用（AC-2.5.5，额度查询恒为 0 次）。
- `routes/loans.py::my_loans_page`：同一函数、每渲染恰好一次（AC-2.5.3/2.5.8），路由无任何手写 COUNT。
- `get_remaining_quota()` docstring 去掉写死的「3」，全源码数字 3 只剩 `config.BORROW_LIMIT` 一处。
- `templates/my_loans.html` 空状态文案改为 AC 原文「当前没有在借物品」；列收敛为名称/借出/应还/状态/归还操作。

## 已交付行为
- 借还后指示实时刷新：借 2 →「已借 2 / 3」，还 1 立即 →「已借 1 / 3」（AC-2.5.4）。
- 逾期 3 天显示「已逾期 3 天」并标红；今天到期的行不标红（AC-2.5.2）。
- 他人记录按 user_id 过滤不可见（AC-2.5.7）。

## 测试
- `tests/test_my_loans.py`：16 例（AC-2.5.1~2.5.9 逐条；AC-2.5.8 参数化 7 个渲染场景含搜索路径，断言额度查询次数列表 == [1]；AC-2.5.9 结构扫描：模板硬编码数字零命中、routes 无 COUNT、services 仅一处聚合）。
- 与 Story 2.2 口径衔接：`test_returns.py` 中 AC-2.2.4「归还后不再标红」在新过滤规则下依然成立（记录直接消失）；15 例原样通过。
- 全量回归：**123 passed**（107→123：本故事 15 例 + NFR-1.3 归还真并发 1 例，零回归）。
- **NFR-1.3 归还真并发直压正式补齐**（deferred-work Story 2.4 遗留项在本故事收口了结）：`tests/test_return_concurrency.py` 复用 concurrency_kit（新增 race_request/race_return 泛化原语），两会话对同一 loan_id 经独立 TCP 连接 barrier 并发 POST /return，20 轮断言状态集合恰 {302, 409}、败方响应体含 ALREADY_RETURNED、returned_at 只写一次且逐轮稳定；逐轮日志入库 concurrency-nfr13-return-20-rounds.log。自此 test_client 冒烟不再是 NFR-1.3 的唯一证据。

## Epic 2 完成定义核验
- ✅ 5 步脚本闭合（首页→搜索→借阅→我的借阅→归还）：test_items/test_loans/test_returns/test_my_loans 覆盖
- ✅ 两个并发用例各 20 轮通过：test_concurrency / test_quota_concurrency 全绿
- ✅ D-021 白盒用例通过：AC-2.3.4 / AC-2.4.4 双故事独立执行
- ✅ grep 证明归还路径不碰 items：AC-2.2.10 零命中断言在回归中持续通过

## Follow-ups
- CSRF 延期口径沿用（deferred-work）。
- AC-2.5.2 的「当天到期」用例依赖测试运行不跨午夜，极端跨日场景由 Story 3.4 回归收口时再评估。
