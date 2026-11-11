---
title: 'Story 3.3 / 3.4：物品停用与恢复上架（D-005 + ADR-007 最终验收）'
type: 'feature'
created: '2026-11-11'
status: 'done'
baseline_commit: '5e02895'
---

# Story 3.3 / 3.4：物品停用与恢复上架

> 本文件一次覆盖人类开工指令要求的两条端点：`POST /admin/items/<id>/unavailable`（Story 3.3）
> 与 `POST /admin/items/<id>/available`（Story 3.4 前半）。Story 3.4 的四态组合矩阵与
> NFR-1.4 交叉比对留在 3.4 收口，范围边界见 §9。

## 1. 三条不可妥协的口径

人类开工指令给出的三条死守线，逐条落到代码与可复跑的断言上：

| # | 口径 | 实现落点 | 证据（可复跑） |
|---|---|---|---|
| ① | **停用不中断借还（D-005）**：允许在「在借」状态停用；停用后借阅者必须能正常归还；归还只写 `loans`，绝不碰 `items.status`（保持 `unavailable`） | `services/admin.py::set_unavailable()` 只写 `items.status` 一个字面量，SQL 里不出现 `loans`；归还路径 `services/loans.py::return_loan()` 自 Story 2.2 起未改（只 `UPDATE loans`）。「归还后仍停用」不是一处 `if`，而是两条写路径**结构上互不相交**的必然结果 | `test_ac_3_3_1_disable_borrowed_item_keeps_active_loan`、`test_ac_3_3_3_borrower_sees_disabled_loan_and_can_return_it`、`test_transitions_never_touch_loans_sql`；§12 核验脚本用例 A |
| ② | **恢复上架（ADR-007）**：`unavailable` → `available`；若此时仍有未归还记录，页面经 LEFT JOIN 渲染出的展示态仍是派生的「在借」，但底层 `items.status` 必须已经是 `available` | `set_available()` 只改存储列；派生结论完全来自 `services/items.py::list_items_with_state()` 的 `CASE WHEN i.status='unavailable' THEN ... WHEN l.id IS NOT NULL THEN 'borrowed'`——本故事**没有**新增第二份派生 SQL（AR-5/PC-8） | `test_ac_3_4_3_restore_while_borrowed_keeps_derived_borrowed_state`（同时断言 `status='available'` 与页面「在借」）；§12 核验脚本用例 B |
| ③ | **严格幂等**：重复停用 / 重复恢复都返回 302 + 提示，绝不 409 | 两条服务函数都是无条件迁移：先判存在（404），再写目标状态；目标状态与当前相同时照常提交。`BizError(409, ...)` 在两条路径上不存在 | `test_ac_3_3_4_repeat_disable_is_idempotent_success`、`test_ac_3_4_2_repeat_restore_is_idempotent_success`、`test_ac_3_4_2_disable_restore_cycle_is_repeatable`、并发幂等 20 轮 × 2 组 |

> **为什么幂等返回 302 而不是 409**：这两条端点的语义是「把物品置为某状态」，不是「从未停用改为停用」。
> 状态机的迁移函数 `f(s) = target` 幂等，`f(f(s)) = f(s)`。重复点击不构成业务冲突，
> 报 409 反而会让管理员在刷新页面后看到「该物品已停用」的错误页——这是纯粹的用户体验事故。
> 与之对照：删除（Story 3.2）是**不可逆**的破坏性操作，第二次删除必须 404，因为它已经没有对象可作用。

## 2. 判定顺序与事务边界

```text
BEGIN IMMEDIATE                    -- write_transaction()，先拿写锁（PC-4）
  ① SELECT id FROM items WHERE id = ?        → 无行：404 RESOURCE_NOT_FOUND（零写入）
  ② UPDATE items SET status = '<目标>' WHERE id = ?   -- 只动一列，不触碰 loans
COMMIT                             -- 幂等：② 命中 0 行（值已相同）也照常提交
```

- **先 404 后写**：不存在的 `item_id` 返回 `RESOURCE_NOT_FOUND`，与删除端点口径一致（PC-9）。
- **不判 409**：两条路径的任何分支都不产生 409；停用与在借可以并存（D-003）。
- **只写一列**：`UPDATE items SET status = ?` 不涉及 `name`/`category`/`created_at`，
  改名禁令（D-007 无名称快照）不受影响。
- **事务内不渲染、不 hash**：`flash` 与 `redirect` 发生在服务返回之后（PC-4）。

## 3. 实现清单

| 文件 | 变更 |
|---|---|
| `services/admin.py` | 新增 `_ensure_item_exists()`（两条迁移共用的存在性判定）+ `set_unavailable()` + `set_available()`；两条各自带一条**字面量** SQL，是 `items.status` 的唯一两个写入点 |
| `routes/admin.py` | 新增 `POST /admin/items/<int:item_id>/unavailable`（flash「已停用」）与 `POST /admin/items/<int:item_id>/available`（flash「已恢复上架」），均 PRG 302；自动受蓝图级 `@bp.before_request` 守卫覆盖（D-012、D-026），路由体内零 role 判断 |
| `templates/admin_items.html` | 「操作」列新增互斥动作按钮：`item.status == 'unavailable'` → 「恢复上架」，否则 → 「停用」；判定用**存储态**而非派生态（在借物品同样可停用）。SSR `form method="post"`，无 fetch/XHR |
| `tests/test_admin_state.py` | 新增 26 例：AC-3.3.1~3.3.7、AC-3.4.1~3.4.3、AC-3.4.8 + 404 边界 + 结构断言 + 并发幂等 20 轮 × 2 |
| `tests/test_admin.py` | 两条范围哨兵同步：`test_ac_3_1_8_...` 从「services/routes 零 `UPDATE items`」改为「恰两处、都在 `services/admin.py`、只写字面量、无 `borrowed`」（AC-3.4.5 判据）；`test_no_edit_or_state_change_endpoints_registered` 更名为 `test_edit_endpoint_stays_unregistered_and_put_unsupported`（编辑与 PUT 仍 404），并新增 `test_state_change_endpoints_reject_get`（GET 两路径 → 405，写操作只接受 POST） |
| `config.py` / `db.py` | 未改：9 个错误码、`CHECK (status IN ('available','unavailable'))` 均在阶段 1 定义，本故事只是把既有约束用起来 |
| `.gitignore` | 新增两份并发证据日志的白名单豁免 |

## 4. AC 对照

| AC | 断言要点 | 测试函数 |
|---|---|---|
| AC-3.3.1 | 在借物品停用 → 302 +「已停用」；`status='unavailable'`；未归还记录逐字段不变 | `test_ac_3_3_1_disable_borrowed_item_keeps_active_loan`<br>`test_ac_3_3_1_disable_never_borrowed_item_also_succeeds` |
| AC-3.3.2 | 匿名 `/items` 与 `?q=` 均不出现；管理列表仍可见且标「已停用」；动作按钮切换为「恢复上架」 | `test_ac_3_3_2_disabled_item_hidden_from_students_but_visible_in_admin_list`<br>`test_ac_3_3_2_available_item_row_offers_disable_action` |
| AC-3.3.3 | 停用后在借记录在 `/my-loans` 仍可见；`POST /return/<id>` 302；`returned_at` 非空且 `status` 仍 `unavailable`；额度释放 | `test_ac_3_3_3_borrower_sees_disabled_loan_and_can_return_it`<br>`test_ac_3_3_3_return_releases_quota_of_disabled_loan` |
| AC-3.3.4 | 重复停用 → 302 +「已停用」，无 409，`status` 不变；重放零副作用 | `test_ac_3_3_4_repeat_disable_is_idempotent_success`<br>`test_ac_3_3_4_repeat_disable_keeps_active_loan_untouched` |
| AC-3.3.5 | 直接写 `'borrowed'` 抛 `IntegrityError`（CHECK）；停用 SQL 只写 `'unavailable'`，全项目 `UPDATE items` 恰两处 | `test_ac_3_3_5_check_constraint_rejects_borrowed_storage_value`<br>`test_ac_3_3_5_disable_sql_only_writes_unavailable_literal` |
| AC-3.3.6 | 学生 → 403 `FORBIDDEN`；匿名 → 302 `/login?next=...`；`items` 零变更 | `test_ac_3_3_6_student_cannot_disable`<br>`test_ac_3_3_6_anonymous_disable_redirects_to_login` |
| AC-3.3.7 | 停用物品上的未归还记录照常计入在借数（额度不释放） | `test_ac_3_3_7_disabled_loan_still_counts_toward_quota` |
| AC-3.4.1 | 恢复 → 302 +「已恢复上架」；`status='available'`；重新出现在 `/items` 与搜索 | `test_ac_3_4_1_restore_returns_item_to_student_view` |
| AC-3.4.2 | 已是 `available` 再恢复 → 302，不报错，状态不变；停用↔恢复可任意往返 | `test_ac_3_4_2_repeat_restore_is_idempotent_success`<br>`test_ac_3_4_2_disable_restore_cycle_is_repeatable` |
| AC-3.4.3 | **D-005 用例 B**：有未归还记录时恢复 → `items.status='available'` 且页面显示「在借」；借阅事实零变更 | `test_ac_3_4_3_restore_while_borrowed_keeps_derived_borrowed_state`<br>`test_ac_3_4_3_restore_then_return_derives_available` |
| AC-3.4.8 | 学生 403 / 匿名 302，`items.status` 不变 | `test_ac_3_4_8_student_cannot_restore`<br>`test_ac_3_4_8_anonymous_restore_redirects_to_login` |

**不属于某条 AC、但属于人类死守线的追加断言**：

- `test_missing_item_returns_404_on_both_transitions`：不存在的 id → 404，`items`/`loans` 零变更。
- `test_transitions_never_touch_loans_sql` / `test_transition_functions_use_write_transaction`：
  两条迁移的函数体（剥掉 docstring 后）既无 `loans`，也都包在 `with write_transaction()` 内。
- `test_no_loans_mutation_across_disable_and_restore`：停用→恢复→停用一整圈后 `loans` 逐字段不变
  （含一条已归还历史记录，证明恢复上架不会「顺带」清理或改写借阅记录）。

## 5. 边界矩阵

| 数据状态 | 动作 | 期望 | 实测 |
|---|---|---|---|
| `available`，无借阅 | 停用 | 302，`unavailable` | ✅ `test_ac_3_3_1_disable_never_borrowed_item_also_succeeds` |
| `available`，**在借** | 停用 | 302，`unavailable`，在借记录保留 | ✅ `test_ac_3_3_1_disable_borrowed_item_keeps_active_loan` |
| `unavailable`，无借阅 | 再次停用 | 302 幂等 | ✅ `test_ac_3_3_4_...` 与并发 20 轮 |
| `unavailable`，在借 | 借阅者归还 | 302，`returned_at` 非空，状态仍 `unavailable` | ✅ `test_ac_3_3_3_...` |
| `unavailable`，无借阅 | 恢复 | 302，`available`，重新可见 | ✅ `test_ac_3_4_1_...` |
| `unavailable`，**在借** | 恢复 | 302，`status='available'`，页面「在借」 | ✅ `test_ac_3_4_3_...` |
| `available` | 再次恢复 | 302 幂等 | ✅ `test_ac_3_4_2_...` |
| 不存在 id | 停用 / 恢复 | 404 `RESOURCE_NOT_FOUND`，零变更 | ✅ `test_missing_item_returns_404_on_both_transitions` |
| 学生 / 匿名 | 两个端点 | 403 / 302，状态不变 | ✅ AC-3.3.6、AC-3.4.8 共四例 |

## 6. 并发幂等实验（20 轮 × 2 组）

**脚手架**：`threading.Barrier(2)` + 2 线程 + **各自独立 `app.test_client()` 与会话**
（与 AC-2.2.9 归并发的既有脚手架同口径；两个请求落在不同连接、不同 session cookie 上）。

| 组 | 实验设定 | 20 轮结果 | 证据日志 |
|---|---|---|---|
| **A 重复停用** | 目标物品含 1 条未归还记录，每轮先由直连 SQL 复位为 `available`；两个管理员会话同时 `POST /unavailable` | **20/20 两方均 302**（无 409）；每轮 `status=unavailable`，`loans` 快照不变 | `concurrency-story33-double-disable-20-rounds.log` |
| **B 重复恢复** | 同一物品含 1 条未归还记录，每轮复位为 `unavailable`；两会话同时 `POST /available` | **20/20 两方均 302**（无 409）；每轮 `status=available`，页面派生态仍为「在借」 | `concurrency-story34-double-restore-20-rounds.log` |

**为什么两会话都成功、不像删除那样一胜一败**：两条迁移都是「写入目标状态」，
后到者执行的是同一条幂等 `UPDATE`，`BEGIN IMMEDIATE` 把两者串行化后结果完全一致。
不存在「第一个赢、第二个发现状态已变」的分支——业务上这两次点击本来就该都成功。

## 7. 结构自检（可 grep / SQL 复核）

| 判据 | 命令 | 结果 |
|---|---|---|
| `items.status` 的写入点 | `grep -n "UPDATE items" services/*.py routes/*.py` | **恰 2 命中**，均在 `services/admin.py`（行 131/149）：`SET status='unavailable'` 与 `SET status='available'` |
| 借阅 / 归还 / 删除路径写 `items.status` | 同上 | **0 命中**（`services/loans.py`、`routes/*.py` 均无） |
| 向 `items.status` 写 `'borrowed'` | `grep -n "borrowed" services/ routes/` | **0 写入**；仅出现在派生查询的 `CASE ... THEN 'borrowed'` 与文档注释里 |
| 迁移函数触碰 `loans` | 函数体（剥 docstring）检索 `loans` | **0 命中**（两条迁移） |
| 存在性判定与写语句同一事务 | 源码顺序断言 | `with write_transaction()` 早于 `UPDATE items` |
| `BEGIN DEFERRED` | 全库检索 | **0** |
| 生产代码 `sqlite3.connect(` | 全库检索 | **1**（`db.py`，未新增） |
| 全库 `role == 'admin'` 授权判定 | `grep -nE "\[.role.\] ?[!=]= ?.admin."` | **1**（`routes/admin.py` 蓝图守卫，未新增第二处） |

## 8. 测试结果

- **本故事新增 26 例全部通过**：`tests/test_admin_state.py`。
- **全量回归：192 passed, 0 failed**（基线 165 + 本故事 26 + `test_admin.py` 新增的 GET-405 哨兵 1 例）。
- 并发幂等 **2 组共 40 轮**真实并发竞争，逐轮断言无例外。
- 复跑命令：`python testtmp/run_pytest.py tests/ -q`（受限沙箱启动器，见 §10）；
  仅本故事：`python testtmp/run_pytest.py tests/test_admin_state.py -v`。
- **人工端到端核验**：`python testtmp/verify_story33.py`，输出见 §12。

## 9. 范围控制

- **只做两条端点**：`/unavailable` 与 `/available`；未注册 `/edit`、未支持 `PUT/PATCH`（编辑功能属人类裁决砍掉的范围，见 `test_edit_endpoint_stays_unregistered_and_put_unsupported`）。
- **AC-3.4.4~3.4.7 留给 Story 3.4 收口**：四态组合矩阵、`GET /my-loans` 四态渲染、NFR-1.4 并发交叉比对
  （列表派生态 ⇔ `loans` 未归还计数）。本故事已提前满足 AC-3.4.5 的 grep 判据（§7 第一行），
  但四态矩阵仍按故事边界留给 3.4，避免把两套断言混在一份交付里。
- **不改锁定值**：借阅限额 3、借期 7 天、六步判定顺序、9 个错误码均未触碰。
- **不新增派生 SQL**：`list_items_with_state()` 是唯一实现，本故事零改动（AR-5、AC-3.4.6）。

## 10. 延期项与已知边界

1. **CSRF**：两个 POST 与既有的新增/删除/借阅/归还同样不带 CSRF token，沿用 PRD §6「明确不做」的既有裁决（`deferred-work.md` 已记录）。
2. **停用/恢复无二次确认**：PRD §4.6 明确「停用是可逆的，误停用不需要救」（UJ-3），
   因此不像删除那样先渲染确认页；恢复上架同理。这是产品裁决，不是遗漏。
3. **操作列按钮不灰化**：管理列表不预告「该物品正在被借，停用后借阅者仍能归还」——列表只渲染动作，
   业务判定留在服务层（PC-1 同口径：确认页/列表不复制业务判定）。
4. **并发证据日志每次测试重写**：沿用 Story 2.5 起的既有延期项；当前共 7 份日志，项目收尾时统一改为「已存在则不覆盖」。
5. **受限环境说明**：本机 DSH 沙箱下 Python 3.14 的 `os.mkdir(mode=0o700)` 会生成当前令牌不可列出的目录，
   导致 pytest `tmp_path` 失败；验证统一用 `testtmp/run_pytest.py` 启动器（在 `.gitignore` 内，非交付代码）。

## 11. 决策回填

| 决策 | 原状态 | 回填后 | 证据 |
|---|---|---|---|
| **D-003**（停用替代强制删除） | 部分已验证 | **已验证** | 在借物品停用 302 且 `loans` 不变（AC-3.3.1）；借阅者仍可归还（AC-3.3.3）；恢复上架 302（AC-3.4.1） |
| **D-005**（停用后归还不回弹） | 待阶段 4（未验证） | **已验证** | 用例 A：`test_ac_3_3_3_...`（`returned_at` 非空且 `status` 仍 `unavailable`）；用例 B：`test_ac_3_4_3_...`（恢复后 `status='available'`、页面「在借」）；两用例**独立存在、未合并** |
| **D-014**（归还只写 loans、状态派生） | 待阶段 4（未验证） | **已验证** | 归还服务全文无 `UPDATE items`（Story 2.2 起）；本故事两条迁移函数体无 `loans`（`test_transitions_never_touch_loans_sql`） |
| **D-015 / ADR-007**（存储态+派生态） | 待阶段 4（未验证） | **已验证** | `items` 表无 `borrowed` 取值（AC-3.3.5）；「在借」由 LEFT JOIN 派生（AC-3.4.3）；两表无任何双写路径（`test_no_loans_mutation_across_disable_and_restore`） |
| **D-020 ③**（`UPDATE items` 仅停用/恢复两处） | 剩余项待 3.3~3.4 | **已验证** | §7 第一行：`services/` + `routes/` 恰 2 命中，均在本故事新增的两个函数里 |

## 12. 人工端到端核验输出（原始）

命令：`python testtmp/verify_story33.py`（真实 Flask 应用 + 完整 WSGI 请求，临时库）。

```text
[前置] 学生 2024001 借阅「投影仪」
  POST /borrow                          status=302 | db_status=available | loans=1

[用例 A] 在借状态下停用，随后借阅者归还（D-005）
  POST /admin/items/<id>/unavailable    status=302 | flash=已停用 | db_status=unavailable | loans_still_there=1 | admin_row=已停用
  匿名 GET /items 学生端可见             visible=否
  匿名 GET /items?q=投影仪              hit=否
  /my-loans 借阅者仍可见该记录            visible=是
  POST /return/<loan_id>                status=302 | returned_at=2026-11-11 19:22:27 | db_status=unavailable | items_untouched=是
  匿名 GET /items 学生端可见             visible=否

[幂等 A] 重复停用（已停用再停用）
  第 1 次重复 POST /unavailable          status=302 | flash=已停用 | error_409=无 | db_status=unavailable
  第 2 次重复 POST /unavailable          status=302 | flash=已停用 | error_409=无 | db_status=unavailable

[用例 B] 恢复上架后仍有未归还记录：存储态 available + 派生态 在借（ADR-007）
  先恢复上架（物品重新对外提供）           status=302 | db_status=available | admin_row=可借
  学生再次借阅（恢复后才可借）             status=302 | active_loans=1 | db_status=available
  在借状态下再次停用                      status=302 | db_status=unavailable
  POST /admin/items/<id>/available      status=302 | flash=已恢复上架 | db_status=available | active_loans=1 | returned_at=None
  学生列表渲染（LEFT JOIN 派生态）        row=在借 | db_status=available
  管理列表渲染                          row=在借

[幂等 B] 重复恢复（已 available 再恢复）
  第 1 次重复 POST /available            status=302 | flash=已恢复上架 | error=无 | db_status=available
  第 2 次重复 POST /available            status=302 | flash=已恢复上架 | error=无 | db_status=available

[收尾] 借阅者归还（派生态应由「在借」回落到「可借」，存储态不变）
  POST /return/<loan_id>                status=302 | db_status=available | student_row=可借

[权限] 学生 / 匿名 调用两个端点
  学生 POST /unavailable                 status=403 | db_status=available
  学生 POST /available                   status=403 | db_status=available
  匿名 POST /unavailable                 status=302 | location=/login?next=/admin/items/6/unavailable
  匿名 POST /available                   status=302 | location=/login?next=/admin/items/6/available

[边界] 不存在的 item_id
  POST /admin/items/99999/unavailable   status=404 | code=RESOURCE_NOT_FOUND
  POST /admin/items/99999/available     status=404 | code=RESOURCE_NOT_FOUND
```

**读数要点**：用例 B 的同一行里 `db_status=available` 与 `row=在借` 并存——存储态回答
「管理员是否对外提供」，派生态回答「此刻是否在别人手上」，两个事实互不覆盖，
这正是 ADR-007 要证明的东西。
