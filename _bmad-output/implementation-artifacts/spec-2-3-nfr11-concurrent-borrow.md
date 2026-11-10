---
title: 'Story 2.3：NFR-1.1 同一物品并发借阅——部分唯一索引的物理兜底'
type: 'feature'
created: '2026-11-10'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '72ec03f'
context:
  - _bmad-output/project-context.md
  - _bmad-output/planning-artifacts/epics.md#story-23
  - _bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/ADR-002-concurrency-uniqueness.md
  - _bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/ADR-005-concurrency-deployment.md
  - _bmad-output/implementation-artifacts/epic-1-context.md
---

## 目标

用硬证据证明「两个人同一秒抢同一件东西，数据库只允许一个人拿到」（NFR-1.1、UJ-4）。
本故事只覆盖物品唯一性；用户额度并发（NFR-1.2）独立留给 Story 2.4，机制不同、不得合并（epics.md Story 2.3 说明条款）。

## 三条铁律的落实方式

1. **真并发，绝不造假**：`start_threaded_server()` 按真实部署形态启动——同进程
   `app.run(threaded=True, use_reloader=False)` 监听随机空闲端口；两名学生各自走真实
   HTTP 登录取得独立会话 cookie；`race_borrow()` 用 `threading.Barrier(2)` 对齐两个
   线程，各自新建 `http.client.HTTPConnection`（独立 TCP 连接）同时 `POST /borrow`。
   日志记录 barrier 释放间隔（实测每轮 0.12~0.23 ms）与每轮胜方（20 轮中 A 胜 7 轮、
   B 胜 13 轮，胜负交替 → 顺序调用不可能产生该分布）。
2. **D-021 白盒直测**：`test_ac_2_3_4_*` 用底层 `sqlite3.connect` 直连（绕过服务层与
   路由）先插一条在借记录，再对同一 `item_id` 插第二条，断言
   `IntegrityError: UNIQUE constraint failed: loans.item_id`，且失败后未归还记录恰 1 条。
   与并发行为测试并列存在、不可相互替代（AC-2.3.4 原文要求）。
3. **断言精确**：每轮断言 HTTP 状态集合 `== {302, 409}`、失败方响应体含
   `ALREADY_BORROWED` 与同源中文文案、`COUNT(item, returned_at IS NULL) == 1`，
   连跑 20 轮无例外（`ROUNDS = 20` 常量固化）。

## 服务层行为修正（AC-2.3.10，本故事暴露的真实缺陷）

`services/loans.py::borrow_item()` 原实现对 `sqlite3.IntegrityError` 无条件映射为
409 `ALREADY_BORROWED`，违反 ADR-002 §4「IntegrityError 必须精确捕获，外键失败等
真实 bug 不得被伪装成业务冲突」。修正为：仅当异常文本含
`UNIQUE constraint failed: loans.item_id` 才映射 409，其余原样上抛（HTTP 500）。
注入方式说明：外键失败无法黑盒真实触发——`borrow_item` ②③ 步对不存在/停用物品
先拦截，永远走不到 INSERT；故测试用连接层替身在 `INSERT INTO loans` 时抛出真实
`sqlite3.IntegrityError("FOREIGN KEY constraint failed")`，分别断言异常类型（不抛
BizError）与真实服务器出口 HTTP 500。

## AC 覆盖

- AC-2.3.1/2/3/8/9 → `test_ac_2_3_1_to_2_3_3_8_9_concurrent_borrow_20_rounds`
  （20 轮真并发；AC-2.3.8 同断言 loans 总行数 == 成功数 20、items 全字段快照逐字节一致；
  AC-2.3.9 断言记录写入证据日志 `concurrency-nfr11-20-rounds.log`，pytest 可重复执行）
- AC-2.3.4 → `test_ac_2_3_4_bypass_service_duplicate_insert_raises_integrity_error`
- AC-2.3.5 → `test_ac_2_3_5_partial_unique_index_shape`
  （PRAGMA index_list：unique=1、partial=1；index_info 列仅 item_id；sqlite_master
  的索引 SQL 含 `WHERE returned_at IS NULL`）
- AC-2.3.6 → `test_ac_2_3_6_returned_item_reborrowable_by_other`（归还后可再借，部分索引不永久占位）
- AC-2.3.7 → `test_ac_2_3_7_no_intermediate_state`（借阅前后 `GET /items` 状态字样与 COUNT 一致）
- AC-2.3.10 → `test_ac_2_3_10_non_unique_integrity_error_is_not_biz_error` +
  `test_ac_2_3_10_http_presents_500_not_409`

## 测试证据

- 命令：`python -m pytest tests/test_concurrency.py -v` → 7 passed（17.37s）
- 命令：`python -m pytest -q`（全量）→ 99 passed（92→99，零回归）
- 20 轮真实并发日志（逐轮胜方与 active_count 证据）：
  `_bmad-output/implementation-artifacts/concurrency-nfr11-20-rounds.log`
- 首轮两处自测失败及修复（如实记录）：
  ① `PRAGMA index_info` 列序取错（name 在第 3 列，误取 cid）→ 修正索引取值；
  ② `test_client(raise_app_exceptions=False)` 在 Werkzeug 3.1 已移除 →
  改为真实 threaded 服务器 + `http.client` 验证 500，与部署形态完全一致。

## 边界（不得互相替代）

- 本故事日志证明的是 NFR-1.1（物品唯一性）。NFR-1.2（用户额度）依赖 Story 2.4 的
  独立并发测试；NFR-1.3（归还并发）已由 Story 2.2 冒烟覆盖机制连通，正式直压与
  Story 2.4 脚手架同批补齐（deferred-work 已登记）。
- 20 轮之间的重置用测试直连 SQL 标记归还（保留行以支撑 AC-2.3.8 计数），
  属测试脚手架行为，不是产品功能。

## 提交

- fix: 精确化 borrow_item 的 IntegrityError 捕获（AC-2.3.10）
- test: Story 2.3 NFR-1.1 真并发验收套件（20 轮 + D-021 白盒）
- docs: 规格 + 冲刺状态 + 延期边界 + 并发证据日志入仓
