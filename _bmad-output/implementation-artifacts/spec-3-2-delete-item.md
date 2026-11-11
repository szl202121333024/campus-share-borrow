---
title: 'Story 3.2：删除物品（在借拦截 + 同事务级联清理）'
type: 'feature'
created: '2026-11-11'
status: 'done'
baseline_commit: 'bf77a25'
---

# Story 3.2：删除物品（在借拦截 + 同事务级联清理）

## 1. 目标与不可妥协的三条口径

Story 3.2 是 Epic 3 唯一带数据破坏性的操作。人类开工指令给出三条死守线，本实现逐条落地，并各自配了可独立执行的证据：

| # | 口径 | 实现落点 | 证据（可复跑） |
|---|---|---|---|
| ① | **危险拦截**：存在未归还记录（`returned_at IS NULL`）时绝不删除，返回 **409 `ITEM_IN_BORROW`**，数据库零变更（快照逐字段一致） | `services/admin.py::delete_item` 的 ② 步：在 `BEGIN IMMEDIATE` 内、任何写语句之前判定；命中即抛 `BizError` 触发 `ROLLBACK` | AC-3.2.1 三例（仅在借 / 在借+已归还混存 / 停用仍在借）；并发 C 组 20 轮双删均 409 |
| ② | **同事务级联清理**：无在借时，删除物品与 `DELETE FROM loans WHERE item_id = ? AND returned_at IS NOT NULL` 必须在同一个 `BEGIN IMMEDIATE` 事务内完成 | `services/admin.py::delete_item` 的 ③④ 步；事务原语为 `db.write_transaction()`（全项目唯一写事务入口，PC-4） | AC-3.2.2 两例；AC-3.2.3 在两条 DELETE 之间注入 `RuntimeError`，断言整体回滚 |
| ③ | **外键兜底**：拒绝 `ON DELETE CASCADE` 隐式级联；显式删除保留可观测性，异常由外键约束兜底 | `db.py` 的 `loans.item_id REFERENCES items(id)` 自始至终不带 `ON DELETE` 子句（D-020）；`delete_item` 仅把 `FOREIGN KEY constraint failed` 精确映射为 409 | AC-3.2.5 三例：`PRAGMA foreign_key_list('loans')` 的 `on_delete = NO ACTION`；源码 DDL 零 `ON DELETE CASCADE`；绕过服务层直删在借物品抛 `IntegrityError` |

> **诚实边界**：在 `BEGIN IMMEDIATE` 串行化之下，② 的业务拦截与 ④ 的外键兜底之间没有可从 HTTP 到达的竞态窗口。外键分支属于**防御性兜底**（防未来代码改动、手工 SQL、逻辑回归），因此用连接层替身做了白盒用例，不把它伪装成「线上可复现路径」。这与 D-021 / ADR-008 的诚实口径一致。

## 2. 判定顺序与事务边界

```text
BEGIN IMMEDIATE                      -- write_transaction()，先拿写锁
  ① SELECT id FROM items WHERE id = ?              → 无行：404 RESOURCE_NOT_FOUND（零写入）
  ② SELECT user_id FROM loans
       WHERE item_id = ? AND returned_at IS NULL
       LIMIT 1                                     → 有行：409 ITEM_IN_BORROW（零写入）
  ③ DELETE FROM loans
       WHERE item_id = ? AND returned_at IS NOT NULL   -- 只清已归还历史
  ④ DELETE FROM items WHERE id = ?                    -- 外键兜底：在借记录仍在则数据库拒绝
COMMIT
```

- **顺序不可交换**：先 ② 再 ③。若先清历史再判在借，混存物品会留下「历史被删、物品还在」的中间态——这正是 AC-3.2.1 第二例要锁死的回归点。
- **③ 只删已归还**：`returned_at IS NOT NULL` 是物理护栏。即使 ② 因未来 Bug 漏判，未归还记录也不会被 ③ 删掉，而会在 ④ 被外键拒绝，随后整笔事务回滚。
- **③④ 同事务**：AC-3.2.3 通过连接层替身在 `DELETE FROM loans` 之后、`DELETE FROM items` 之前抛 `RuntimeError`，断言物品仍在、已归还记录条数不变、`items`/`loans` 快照逐字段一致。
- **404 先于 409**：不存在与在借同时成立时返回 404（资源不存在优先），与 PC-9「真实 4xx + 已定义错误码」一致。
- **事务内不做渲染/哈希/网络**：路由只在服务返回后 `flash` 与 `redirect`（PC-4）。

## 3. 实现清单

| 文件 | 变更 |
|---|---|
| `services/admin.py` | 新增 `get_item()`（确认页存在性查询）与 `delete_item()`（判定顺序 + 显式级联 + 外键精确映射）；`_FK_LOANS_ITEM` 常量只匹配 `FOREIGN KEY constraint failed` |
| `routes/admin.py` | 新增 `GET /admin/items/<int:item_id>/delete`（确认页，200，`Cache-Control: no-store`）与 `POST /admin/items/<int:item_id>/delete`（PRG 302 + flash「已删除」）；二者自动受蓝图级 `@bp.before_request` 守卫覆盖（D-026） |
| `templates/admin_delete_confirm.html` | 新增：物品名称、类别、状态、「确认删除」按钮；`form method="post"` 指向删除路由 |
| `templates/admin_items.html` | 列表新增「操作」列与「删除」链接（指向确认页）；空表 `colspan` 5→6 |
| `config.py` | 未改：`ITEM_IN_BORROW` 与中文文案「该物品在借中，无法删除」在阶段 1 已定义，9 个错误码口径不变 |
| `db.py` | 未改：`loans.item_id` 外键本就不带 `ON DELETE CASCADE`（D-020），本故事用测试把该事实钉死 |
| `tests/test_admin.py` | 范围哨兵同步：删除端点已注册，从「必须 404」清单移除；编辑/停用/恢复仍必须 404 |
| `tests/test_admin_delete.py` | 新增 24 例：AC-3.2.1~3.2.7 + 外键白盒 + 串行/并发边界 |

## 4. AC 对照

| AC | 断言要点 | 测试函数 |
|---|---|---|
| AC-3.2.1 | 在借 → 409 `ITEM_IN_BORROW`，提示文案同源；`items`/`loans` 快照逐字段不变 | `test_ac_3_2_1_active_loan_blocks_delete_without_any_mutation`<br>`test_ac_3_2_1_mixed_history_is_not_partially_cleaned`<br>`test_ac_3_2_1_unavailable_item_with_active_loan_still_409` |
| AC-3.2.2 | 无在借 + 3 条已归还 → 302 + 「已删除」；物品行删除；名下 `loans` 归零 | `test_ac_3_2_2_returned_history_is_cascade_cleaned`<br>`test_ac_3_2_2_delete_only_cleans_target_items_history` |
| AC-3.2.3 | `DELETE loans` 后、`DELETE items` 前注入异常 → 整体回滚，无中间态 | `test_ac_3_2_3_exception_between_cascade_and_item_delete_rolls_back` |
| AC-3.2.4 | 不存在的 `item_id` → 404 `RESOURCE_NOT_FOUND`，零变更 | `test_ac_3_2_4_missing_item_returns_404` |
| AC-3.2.5 | `PRAGMA foreign_key_list('loans')` 的 `item_id.on_delete ≠ CASCADE`；DDL 无隐式级联；直删在借物品抛外键错误 | `test_ac_3_2_5_item_foreign_key_is_not_cascade`<br>`test_ac_3_2_5_schema_and_delete_path_have_no_implicit_cascade`<br>`test_app_connection_enables_foreign_keys`<br>`test_fk_backstop_direct_delete_of_active_item_raises` |
| AC-3.2.6 | 确认页 200、含名称与「确认删除」按钮；GET 删除路径不产生删除；只接受 POST | `test_ac_3_2_6_confirm_page_renders_without_deleting`<br>`test_ac_3_2_6_get_delete_path_never_deletes`<br>`test_ac_3_2_6_confirm_page_of_missing_item_is_404` |
| AC-3.2.7 | 学生 GET/POST → 403 `FORBIDDEN`；匿名 → 302 `/login?next=`；数据不变 | `test_ac_3_2_7_student_get_and_post_are_forbidden_with_untouched_data`<br>`test_ac_3_2_7_anonymous_get_and_post_redirect_to_login` |

**D-010 / D-020 追加防线**（不属于某条 AC，但属于人类死守线）：

- `test_fk_backstop_maps_to_item_in_borrow_and_restores_history`：连接层替身让 ② 漏判，④ 撞外键 → 映射 409 `ITEM_IN_BORROW`，且被 ③ 删掉的历史随回滚恢复。
- `test_non_fk_integrity_error_is_not_disguised_as_409`：`CHECK constraint failed` 原样上抛，遵守 ADR-008「只映射唯一/外键特征串」。
- `test_second_serial_delete_is_404`：同一物品串行删两次，第二次 404。
- 并发三组见 §6。

## 5. 边界矩阵（Epic 3 完成定义的四类边界全覆盖）

| 数据状态 | 期望 | 实测 |
|---|---|---|
| 物品**在借**（`returned_at IS NULL`） | 409 `ITEM_IN_BORROW`，零变更 | ✅ `test_ac_3_2_1_active_loan_blocks_delete_without_any_mutation` |
| 在借 + 已归还**混存** | 409，且已归还记录**不被提前清理** | ✅ `test_ac_3_2_1_mixed_history_is_not_partially_cleaned` |
| 物品**停用**且仍在借 | 409（停用不构成删除许可） | ✅ `test_ac_3_2_1_unavailable_item_with_active_loan_still_409` |
| 物品**停用**且无借阅 | 302 删除成功 | ✅ `test_boundary_unavailable_item_without_loans_deletes_cleanly` |
| 物品有**已归还记录**、无在借 | 302；物品与其名下 `loans` 全部归零 | ✅ `test_ac_3_2_2_returned_history_is_cascade_cleaned` |
| 物品**从未被借过** | 302；无 `loans` 残留 | ✅ `test_boundary_never_borrowed_item_deletes_cleanly` |
| 其他物品也有已归还记录 | 只清目标物品，别的物品历史不动 | ✅ `test_ac_3_2_2_delete_only_cleans_target_items_history` |
| 不存在的 `item_id` | 404 `RESOURCE_NOT_FOUND` | ✅ `test_ac_3_2_4_missing_item_returns_404` |
| 同一物品串行删两次 | 第一次 302，第二次 404 | ✅ `test_second_serial_delete_is_404` |

## 6. 并发实验（真实 threaded 服务器 + barrier + 独立 TCP 连接）

**脚手架**：`tests/concurrency_kit.py::start_threaded_server`（单进程 `app.run(threaded=True)`）+ `race_request`（`threading.Barrier(2)`、各自独立 TCP 连接与会话 cookie）。每组 20 轮，逐轮写证据日志。

| 组 | 实验设定 | 20 轮结果 | 证据日志 |
|---|---|---|---|
| **A 双删** | 目标物品无在借、含 2 条已归还；两个管理员会话同时 `POST /admin/items/<id>/delete` | **20/20 恰为 `{302, 404}`**（谁先谁后随机）；每轮 `items=0`、`loans=0`，无中间态 | `concurrency-story32-double-delete-20-rounds.log` |
| **B 删除 vs 借阅** | 目标物品无在借、含 1 条已归还；管理员删除 与 学生 `POST /borrow` 同时发出 | **20/20 只出现两种结局**：12 轮 `delete=409 / borrow=302`（借阅先赢），8 轮 `delete=302 / borrow=404`（删除先赢）；无一例「无物品却有在借」 | `concurrency-story32-delete-vs-borrow-20-rounds.log` |
| **C 在借双删** | 目标物品有 1 条未归还记录；两个管理员会话同时删 | **20/20 两边均 409 `ITEM_IN_BORROW`**；每轮 `items`/`loans` 快照逐字段不变 | 由 `test_concurrent_delete_of_in_borrow_item_both_409` 断言（不另写日志） |

**竞态解释**：删除与借阅都在 `BEGIN IMMEDIATE` 内完成判定与写入，SQLite 的写锁把两者串行化。后到者在对方提交后才开始判定，因此只可能看到「物品已消失 → 404」或「在借记录已存在 → 409」，不存在「双方都检查通过」的窗口。这正是 ② 的业务拦截优先于 ④ 外键兜底的原因。

## 7. 结构自检（可 grep / SQL 复核）

| 判据 | 结果 |
|---|---|
| `db.py` DDL 出现 `ON DELETE CASCADE` | **0**（`loans.item_id REFERENCES items(id)` 无 `ON DELETE` 子句） |
| `PRAGMA foreign_key_list('loans')` 的 `item_id.on_delete` | **`NO ACTION`**（测试断言恰为该值，不是仅「非 CASCADE」） |
| 生产连接 `PRAGMA foreign_keys` | **1**（`db.get_db()` 四项 PRAGMA 之一；测试断言） |
| `services/admin.py` 的显式级联 SQL | `DELETE FROM loans WHERE item_id = ? AND returned_at IS NOT NULL` **恰 1 处**；位于 `DELETE FROM items WHERE id = ?` 之前，且都在 `with write_transaction()` 内 |
| `services/` 出现 `UPDATE items` | **0**（删除不碰物品状态；3.3/3.4 才会有合法的状态变更） |
| 生产代码 `sqlite3.connect(` | **1**（`db.py:93`；`tests/` 白盒脚手架按既有口径豁免） |
| 生产代码 `BEGIN DEFERRED` | **0** |
| 全库 `role == 'admin'` 授权判定 | **1**（`routes/admin.py` 蓝图 `before_request`；D-026 结构测试锁定） |
| 向 `items.status` 写 `'borrowed'` | **0**（AR-4；既有结构测试覆盖） |
| 删除路径的 `IntegrityError` 捕获 | 仅 `FOREIGN KEY constraint failed` 映射 409；其余原样上抛（ADR-008） |

## 8. 测试结果

- **Story 3.2 新增 24 例全部通过**；文件：`tests/test_admin_delete.py`。
- **全量回归：165 passed, 0 failed**（Story 3.1 的 18 例、Story 1.x/2.x 的 123 例均未回归；基线 141 + 本故事 24 = 165）。
- 并发三组共 **60 轮**真实 HTTP 竞争，逐轮断言无例外。
- 复跑命令（正常开发机）：`python -m pytest tests/ -q`；仅本故事：`python -m pytest tests/test_admin_delete.py -v`。
- 受限环境说明：本机 DSH 沙箱下 Python 3.14 的 `os.mkdir(mode=0o700)` 会生成当前令牌不可列出的目录，导致 pytest `tmp_path` 失败；验证时用 `testtmp/run_pytest.py` 启动器把测试临时目录模式放宽为 `0o777`。该启动器在 `.gitignore` 内，**不属于交付代码**，不影响生产路径。

## 9. 范围控制与回归

- **只做 3.2**：未注册 `/admin/items/<id>/edit`、`/unavailable`、`/available`；`tests/test_admin.py` 的范围哨兵继续断言这些路径对学生 404。
- **无编辑功能**：沿用人类裁决（改名会破坏借阅历史名称一致性，D-007 已砍快照字段）。
- **无 JSON / fetch / XHR**：确认页与删除均为 SSR `form method="post"`。
- **无 `ON DELETE CASCADE`**：数据库层不替业务做决定。
- **不改锁定值**：借阅限额 3、借期 7 天、六步判定顺序、9 个错误码均未触碰。

## 10. 延期项与已知边界

1. **CSRF**：删除 POST 与新增/归还/借阅同样不带 CSRF token，沿用 PRD §6「明确不做」的既有裁决，记入 `deferred-work.md`。
2. **确认页不预告「在借不可删」**：确认页只渲染名称/类别/状态；在借物品会在提交后得到 409。原因：确认页不应复制业务判定（PC-1），且 AC-3.2.6 只要求名称与按钮。若未来要做「灰掉删除按钮」，应由管理列表的派生状态驱动，而不是在确认页再查一次在借。
3. **外键兜底分支白盒可达、HTTP 不可达**：见 §1 诚实边界；保留该分支作为防御性代码，并用连接层替身锁定映射行为。
4. **并发证据日志每次测试重写**：沿用 Story 2.5 已记录的延期项；当前共 5 份日志（nfr11/nfr12/nfr13 + story32 双删/删借对抗），项目收尾时统一改为「已存在则不覆盖」。

## 11. 决策回填

- **D-010**（删除物品与历史记录）：事后验证由「（未验证）」回填为「已验证」，证据为本故事 AC-3.2.2 / AC-3.2.1 两方向。
- **D-020**（ADR-002 三处加严）：① 外键不带 `ON DELETE CASCADE` 由本故事 `PRAGMA` 与直删白盒用例验证；②③ 归还侧已由 Story 2.2/2.5 验证。
- **D-026**（蓝图级 403）：删除确认页与删除 POST 均挂在 `/admin` 蓝图下，自动受同一 `before_request` 守卫覆盖；AC-3.2.7 双角色用例复验。
