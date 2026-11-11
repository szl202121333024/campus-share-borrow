---
title: 'Story 3.4：四态组合矩阵与 NFR-1.4 并发交叉比对（终局回归）'
type: 'feature'
created: '2026-11-11'
status: 'done'
baseline_commit: 'aaa15ee'
---

# Story 3.4：四态组合矩阵与 NFR-1.4 并发交叉比对

> 本故事是第十二个（最后一个）故事，承担两件此前刻意留到收口的事：
> **AC-3.4.4 四态组合矩阵** 与 **AC-3.4.7 NFR-1.4 并发交叉比对**。
> 本故事**零产品代码改动**——`services/`、`routes/`、`templates/` 一行未动，
> 交付物是测试、证据与文档；这本身就是 ADR-007「存储态 + 派生态」设计成立的旁证：
> 四种组合不需要新增任何分支，只需要把既有派生查询的渲染结果核对一遍。

## 1. 三条不可妥协的口径

| # | 口径 | 落点 | 证据（可复跑） |
|---|---|---|---|
| ① | **四种组合必须各有独立断言，且两个列表全部交叉核对** | `tests/test_four_state_matrix.py` 的四个 `test_combination_*` 逐个组合核对 `/items`、搜索、`/my-loans`、`/admin/items`；`test_four_combinations_cross_rendered_in_one_state` 把四种组合放进同一个库状态、一次渲染再交叉核对 | 8 个用例全绿；§2 矩阵表；§11 人工核验输出 |
| ② | **展示优先级恒为 unavailable > borrowed > available** | 派生 SQL 的 `CASE WHEN i.status='unavailable' THEN ... WHEN l.id IS NOT NULL THEN 'borrowed'`（Story 3.3 前既有，本故事零改动）。组合 D（停用 + 在借）在管理列表渲染为「已停用」而不是「在借」，但仍在借人列如实显示 `陈默` | `test_combination_4_unavailable_with_loan_hidden_but_returnable`；矩阵用例第 4 步 |
| ③ | **并发结束后不允许出现中间态，且判据对每一件物品成立** | `tests/test_nfr14_cross_check.py::_cross_check()` 每轮同时核对学生列表 / 我的借阅 / 管理列表与 `loans` 未归还计数，并额外断言「没有指向已删除物品的借阅记录」 | 20 轮借阅对抗 + 20 轮四操作交叉，逐轮一致；§4 |

## 2. 四态组合矩阵（AC-3.4.4）

存储态只有两个取值，「在借」由 `loans` 派生，于是恰有四种组合。两个列表的交叉核对结果：

| 组合 | `items.status` | 未归还记录 | `GET /items`（学生） | `GET /my-loans`（借阅者） | `GET /admin/items` | 搜索 `?q=` |
|---|---|---|---|---|---|---|
| **A** | `available` | 无 | **可借**（有借阅按钮） | 不出现（空状态文案） | 可借 + 「停用」动作 | 命中 |
| **B** | `available` | 有 | **在借** + 应还日期 + 借阅人，**无**借阅按钮 | **在借** + 借阅时间 + 归还按钮 | 在借 + 在借人 | 命中 |
| **C** | `unavailable` | 无 | **不出现** | 不出现 | 已停用 + 「恢复上架」动作 | 不命中 |
| **D** | `unavailable` | 有 | **不出现**（停用优先） | **在借** + 归还按钮（可见、可归还） | **已停用**（优先级高于在借）+ 在借人 | 不命中 |

**四条独立用例各自锁定的东西**：

| 用例 | 独立断言要点 |
|---|---|
| `test_combination_1_available_without_loan_shows_available` | 匿名与学生视图都渲染「可借」；**只有这一种组合给出借阅入口**（`action="/borrow"` + 正确 `item_id`）；`/my-loans` 渲染空状态文案 |
| `test_combination_2_available_with_loan_shows_borrowed` | 应还日期列有值、借阅人列 = `林晓`、**没有**借阅入口；借阅者 `/my-loans` 出现该行且含归还表单；**另一个学生看不到**；管理列表同上 |
| `test_combination_3_unavailable_without_loan_is_hidden` | 列表与搜索**双路径**都不出现；管理列表标「已停用」、应还日期与在借人都是 `—`、动作切换为「恢复上架」 |
| `test_combination_4_unavailable_with_loan_hidden_but_returnable` | 学生端不可见 + 借阅者可见可归还 + 管理列表「已停用」且在借人如实显示；归还后 `items.status` **仍是** `unavailable`（D-005 用例 A 在渲染层的复验） |

**矩阵用例**（`test_four_combinations_cross_rendered_in_one_state`）把 A/B/C/D 同时建进一个库，
然后用六个断言把「渲染 ⇔ 事实」钉死：匿名与登录态一致、搜索集合恰为 `{A, B}`、
`/my-loans` 每个借阅者恰一行、管理列表四行且优先级正确、
以及**逐物品**核对 `expected = 已停用 / 在借 / 可借`（右半边是真库直连 SQL，不经应用层）。

## 3. 派生唯一实现（AC-3.4.6）

| 判据 | 命令 | 结果 |
|---|---|---|
| `list_items_with_state` 定义 | `grep -rn "def list_items_with_state" services/ routes/` | **1 处**（`services/items.py:16`） |
| 「物品联 loans 未归还记录」派生 SQL | `grep -rni "LEFT JOIN loans" services/ routes/` | **1 处**（`services/items.py:33`） |
| 其它服务私自构造 `'borrowed'` | 剥 docstring 后检索 `'borrowed'` | **0 处**（仅 `items.py` 的派生 `CASE` 与 `admin.py` docstring 的说明文字） |
| 模板自己算在借 | 检索 `templates/*.html` 的 `returned_at` / `LEFT JOIN` | **0 处**；三个模板都只读 `item.display_state` |

**行为侧证据**（`test_ac_3_4_6_every_list_calls_the_single_derivation`）：
把 `list_items_with_state` 换成探针后连打三条路径，调用序列恰为
`[({"query": None}), ({"query": "算法"}), ({"include_unavailable": True})]` ——
学生列表、搜索结果、管理列表**确实**共用同一函数，而不是各写一份长得像的 SQL。

## 4. NFR-1.4 并发交叉比对（AC-3.4.7）

### 4.1 判据怎么写成可执行的

`_cross_check()` 每轮做四件事，全部用**直连 SQL**（不经应用层）作为事实基准：

1. **孤儿检查**：`loans LEFT JOIN items` 中不存在 `i.id IS NULL` 的行 ——
   删除路径不许留下「有记录、无物品」的残骸；
2. **唯一性**：每件物品的未归还计数 ∈ {0, 1}（部分唯一索引的并发面）；
3. **学生列表 + 我的借阅**：可见集合 = 非停用物品；每行文案必须等于
   `在借 ⇔ active=1` / `可借 ⇔ active=0`；每个学生 `/my-loans` 的行集合必须等于
   该学生的未归还记录集合（既查「有记录却显示可借」，也查「无记录却显示在借」）；
4. **管理列表**：覆盖全量、每件一行，文案按 `unavailable > borrowed > available` 复算。

任何一条不符都会以「第 N 轮：某物品渲染=X 事实=Y」的形式失败 ——
断言里直接写出这两个数，评审不需要回查日志。

### 4.2 实验一：借阅对抗（复用 Story 2.3 的 20 轮实验）

`threading.Barrier(2)` + 两个独立 TCP 连接与会话，同时 `POST /borrow` 抢同一件物品；
每轮结束立刻做全表交叉比对，然后用直连 SQL 把本轮记录标记归还（脚手架复位）。

| 指标 | 结果 |
|---|---|
| 20 轮状态集合 | 20/20 恰 `{302, 409}`，409 方响应体含 `ALREADY_BORROWED` |
| 未归还计数 | 20/20 恰 1 |
| 渲染 | 20/20 该物品在学生列表与我的借阅里都是「在借」，持有者恰为胜方 |
| 交叉比对 | 20/20「三张表 ⇔ 库」一致 |
| 胜方分布 | 学生A 9 轮 / 学生B 11 轮（分布均衡，不是单边抢跑） |
| barrier 释放间隔 | 0.10 ~ 0.30 ms |
| 证据日志 | `concurrency-story34-nfr14-borrow-crosscheck-20-rounds.log` |

### 4.3 实验二：四操作交叉（本故事新增的高压场景）

这是四条写路径**第一次在同一瞬间相遇**：借阅只写 `loans`、归还只写 `loans`、
删除写 `items` + `loans`、停用只写 `items.status`。每轮新建一件 `available` 物品并预置
1 条未归还记录（持有人 = 学生A），然后 `Barrier(4)` 对齐、四个请求同时打向这件物品。

| 指标 | 结果 |
|---|---|
| 20 轮状态集合 | 四条路径均落在语义允许集合内：借阅 ∈ {302,404,409}、归还 = 302、删除 ∈ {302,409}、停用 ∈ {302,404}；**0 次 5xx** |
| 结局分布 | 删除成功 10 轮 / 被在借拦截 10 轮；借阅成功 3 轮（归还先落地才有机会）；停用 19 轮 302 + 1 轮 404（round 12，物品已被删除） |
| 关键互斥校验 | 借阅成功 ⇒ 删除必然 409 且未归还计数 = 1；删除成功 ⇒ 该物品的借阅记录（含已归还）全部归零，借阅只能是 404/409 |
| 交叉比对 | 20/20「三张表 ⇔ 库」一致，**无任何一轮出现「有记录却显示可借」或「无记录却显示在借」** |
| barrier 释放间隔 | 0.23 ~ 2.20 ms |
| 证据日志 | `concurrency-story34-nfr14-four-way-20-rounds.log` |

**为什么四种结局都能出现却没有一次中间态**：四条写路径的判定与写入都在
`BEGIN IMMEDIATE` 内完成（PC-4），SQLite 的写锁把它们排成某个全序；无论这个全序是什么，
提交后的库状态都是自洽的，而渲染侧的四种组合又全部由同一条派生查询算出（AC-3.4.6），
所以「事实」与「渲染」之间没有可以漂移的缝隙。日志里 20 轮出现了
「删除赢 / 借阅赢 / 停用后借阅被拦 / 归还先落地」四种真实交错，正是这段推理的实证。

## 5. AC 对照（Story 3.4 全部八条）

| AC | 断言要点 | 测试函数 | 交付故事 |
|---|---|---|---|
| AC-3.4.1 | 恢复 → 302「已恢复上架」；`status='available'`；重新出现在 `/items` 与搜索 | `test_ac_3_4_1_restore_returns_item_to_student_view` | 3.3 |
| AC-3.4.2 | 已是 `available` 再恢复 → 302、不报错、状态不变；停用↔恢复可任意往返 | `test_ac_3_4_2_repeat_restore_is_idempotent_success`<br>`test_ac_3_4_2_disable_restore_cycle_is_repeatable` | 3.3 |
| AC-3.4.3 | **D-005 用例 B**：有未归还记录时恢复 → `status='available'` 且页面「在借」；借阅事实零变更 | `test_ac_3_4_3_restore_while_borrowed_keeps_derived_borrowed_state`<br>`test_ac_3_4_3_restore_then_return_derives_available` | 3.3 |
| **AC-3.4.4** | 四态组合各有独立断言；优先级 `unavailable > borrowed > available`；组合 D 学生端不展示但借阅者可归还 | `test_combination_1_available_without_loan_shows_available`<br>`test_combination_2_available_with_loan_shows_borrowed`<br>`test_combination_3_unavailable_without_loan_is_hidden`<br>`test_combination_4_unavailable_with_loan_hidden_but_returnable`<br>`test_four_combinations_cross_rendered_in_one_state` | **3.4** |
| AC-3.4.5 | 全项目 `UPDATE items` 恰两处（停用/恢复），借阅/归还/删除路径 0 命中 | `test_ac_3_3_5_disable_sql_only_writes_unavailable_literal` | 3.3 |
| **AC-3.4.6** | `list_items_with_state(...)` 是唯一派生实现；三张列表均复用它 | `test_ac_3_4_6_derivation_is_implemented_only_once`<br>`test_ac_3_4_6_every_list_calls_the_single_derivation` | **3.4** |
| **AC-3.4.7** | 并发结束后「列表派生态 ⇔ `loans` 未归还计数」，无中间态 | `test_nfr_1_4_borrow_race_list_matches_counts_20_rounds`<br>`test_nfr_1_4_four_operation_race_never_leaves_intermediate_state` | **3.4** |
| AC-3.4.8 | 学生 → 403 `FORBIDDEN`；匿名 → 302 登录页；`items.status` 不变 | `test_ac_3_4_8_student_cannot_restore`<br>`test_ac_3_4_8_anonymous_restore_redirects_to_login` | 3.3 |

**不属于某条 AC、但属于本次要求的追加断言**：

- `test_row_probe_rejects_duplicate_rows`：页面探针自检——同一物品在一页渲染两次必须
  当场失败（`LEFT JOIN` 翻倍是 NFR-1.4 的一类中间态，不能被后续断言掩盖）。
- `_cross_check()` 里的孤儿记录检查：删除成功后不允许存在指向该物品的借阅记录。

## 6. 结构自检（可 grep 复核）

| 判据 | 命令 | 结果 |
|---|---|---|
| `items.status` 写入点 | `grep -n "UPDATE items" services/*.py routes/*.py` | **恰 2 处**：`services/admin.py:131`（`'unavailable'`）、`:149`（`'available'`） |
| 唯一派生实现 | `grep -rn "def list_items_with_state" services/ routes/` | **1 处**：`services/items.py:16` |
| 派生 SQL | `grep -rni "LEFT JOIN loans" services/ routes/` | **1 处**：`services/items.py:33` |
| 角色授权判定 | `grep -nE "\[.role.\] ?[!=]= ?.admin." services/ routes/` | **1 处**：`routes/admin.py:47`（蓝图守卫，未新增） |
| 生产代码连接入口 | `grep -n "sqlite3.connect" db.py services/ routes/` | **1 处调用**：`db.py:93`（`db.py:3` 是 docstring 里的规则说明，不是调用） |
| `BEGIN DEFERRED` | 全库检索 | **0** |
| 本故事是否触碰产品代码 | `git diff --stat aaa15ee..HEAD -- services routes templates app.py config.py db.py` | **空**（零改动） |

## 7. 测试结果

- **新增 10 例**：`tests/test_four_state_matrix.py`（8 例，含探针自检）、
  `tests/test_nfr14_cross_check.py`（2 例）。
- **全量回归：202 passed, 0 failed**（基线 192 + 本次 10），耗时 8 分 24 秒。
- 并发实验合计新增 **2 组共 40 轮**真实并发；连同既有故事，仓库内并发实验共
  **10 组 200 轮**（NFR-1.1 / 1.2 / 1.3、双删、删借对抗、在借双删、重复停用、重复恢复、
  借阅对抗、四操作交叉），其中 **9 组留有逐轮证据日志**（在借双删用例只做断言、不写日志）。
- 复跑命令：`python testtmp/run_pytest.py tests/ -q`（受限沙箱启动器，见 §11 说明）；
  仅本故事：`python testtmp/run_pytest.py tests/test_four_state_matrix.py tests/test_nfr14_cross_check.py -v`。
- **工作树零污染验证**：全量回归跑完后 `git status --short` 只剩本轮人工编辑的文档，
  七份既有并发日志与两份新增日志**逐字节未变**（§9 的延期项收口）。

## 8. 范围控制

- **不新增产品代码**：四种组合完全由既有派生查询渲染，本故事只增加断言。
- **不新增端点**：恢复上架与停用在 Story 3.3 已交付，本故事不注册任何路由。
- **不改锁定值**：借阅限额 3、借期 7 天、六步判定顺序、9 个错误码均未触碰。
- **不把并发实验写成「随机压测」**：每轮起点确定（新建 available 物品 + 1 条未归还记录），
  断言的是**不变量**而不是某个具体结局，因此日志里出现四种不同交错仍然全绿。
- **测试脚手架与产品能力分开**：`tests/page_probe.py`、`tests/concurrency_kit.py`、
  每轮的直连 SQL 复位都属 tests/ 内脚手架，评审时不得当作产品能力。

## 9. 延期项收口（本次一并了结）

| 延期项 | 登记处 | 收口方式 | 验证 |
|---|---|---|---|
| 20 轮证据日志被每次测试无条件覆写（累计七份） | Story 2.5 / 3.2 / 3.3 段 | 新增 `tests/concurrency_kit.py::write_evidence_log()`：**已存在则不覆盖**；五处写日志的用例（七份日志）全部改走该函数 | 复跑 `tests/test_return_concurrency.py` 后 `git status` 对 `concurrency-nfr13-return-20-rounds.log` 零变更；全量 202 例跑完后工作树无日志 diff |
| AC-3.4.4~3.4.7 留在 3.4 收口 | Story 3.3 段 | 本故事交付 §2~§4 | 10 个新用例全绿；§11 人工核验输出 |
| NFR-1.3 归还真并发 | Story 2.4 段 | Story 2.5 已了结（保留记录） | — |

**刷新证据的新口径**：需要重新生成某份并发日志时，先手动删除对应 `.log` 再跑用例。
宁可证据「旧而真」，也不要「新而脏」地覆盖既有验收数据。

## 10. 决策回填

| 决策 | 原状态 | 回填后 | 证据 |
|---|---|---|---|
| **D-005**（停用后归还不回弹） | 已验证（3.3） | 保持**已验证**，并补渲染层证据 | 组合 D 用例：停用 + 在借时借阅者可见可归还，归还后 `status` 仍 `unavailable` |
| **D-014 / D-015 / ADR-007**（存储态 + 派生态） | 已验证（3.3） | 保持**已验证**，并补「四态渲染矩阵」证据 | §2 矩阵表：四种组合全部由同一派生查询渲染，产品代码零改动 |
| **D-020 ③**（`UPDATE items` 仅两处） | 已验证（3.3） | 保持**已验证** | §6 第一行复核：仍恰 2 处，本故事未新增 |
| **NFR-1.4**（无中间态） | 分散验证（2.3 单场景） | **已验证（收口）** | §4：20 轮借阅对抗 + 20 轮四操作交叉，逐轮全表交叉比对无例外 |

本故事**未触发新的需求裁决**：四条口径都已在阶段 1~3 锁定（ADR-007、D-005、D-014、NFR-1.4），
本故事只是把它们变成可复跑的断言，因此 `decision-log.md` 不新增条目（下一可用编号仍为 **D-027**）。

## 11. 人工端到端核验输出（原始）

命令：`python testtmp/verify_story34.py`（真实 Flask 应用 + 完整 WSGI/HTTP 请求 + 临时库）。

```text
========================================================================================================
Story 3.4 核验 1／2：四态组合矩阵（available/unavailable × 无在借/在借）
========================================================================================================

  [组合] 存储态 / 未归还 / 学生列表 / 我的借阅 / 管理列表 / 搜索
  ------------------------------------------------------------------------------------------------
  A 四态A可借无借: status=available active=0 | /items=可借 | /my-loans=不出现 | /admin=可借 | 搜索=命中
  B 四态B可借在借: status=available active=1 | /items=在借 | /my-loans=在借 | /admin=在借 | 搜索=命中
  C 四态C停用无借: status=unavailable active=0 | /items=不出现 | /my-loans=不出现 | /admin=已停用 | 搜索=不命中
  D 四态D停用在借: status=unavailable active=1 | /items=不出现 | /my-loans=在借 | /admin=已停用 | 搜索=不命中

  [组合 B] 借阅者视角 /my-loans 明细：在借（学生A） / 不出现（学生B）
  [组合 D] 停用 + 在借：学生端 不出现，借阅者 可见，管理列表 已停用

  矩阵交叉比对（三张表 <-> 库）：一致

========================================================================================================
Story 3.4 核验 2／2：四操作交叉（借阅 + 归还 + 删除 + 停用，真并发）
========================================================================================================

  [结构] list_items_with_state 定义数=1 | services+routes 中 LEFT JOIN loans 出现次数=1 | items.py 含 display_state 派生=True
  部署形态: threaded=True, host=127.0.0.1, port=50209

  [轮次] 借阅 / 归还 / 删除 / 停用 -> 物品 / 未归还 / 交叉比对
  ------------------------------------------------------------------------------
  round 01: borrow=302 return=302 delete=409 disable=302 -> item=保留 active=1 | barrier 间隔=0.51ms | 交叉比对=一致
  round 02: borrow=409 return=302 delete=409 disable=302 -> item=保留 active=0 | barrier 间隔=0.35ms | 交叉比对=一致
  round 03: borrow=404 return=302 delete=302 disable=302 -> item=已删除 active=0 | barrier 间隔=0.48ms | 交叉比对=一致
  round 04: borrow=409 return=302 delete=409 disable=302 -> item=保留 active=0 | barrier 间隔=0.46ms | 交叉比对=一致
  round 05: borrow=409 return=302 delete=302 disable=302 -> item=已删除 active=0 | barrier 间隔=0.37ms | 交叉比对=一致
  round 06: borrow=404 return=302 delete=302 disable=302 -> item=已删除 active=0 | barrier 间隔=0.55ms | 交叉比对=一致

========================================================================================================
核验结束。数据库： <临时目录>/verify.sqlite
========================================================================================================
```

**读数要点**：矩阵块的 D 行同时出现「`/items` 不出现」与「`/my-loans` 在借」——
停用回答「是否对外提供」、在借回答「此刻是否在别人手上」，两个事实互不覆盖（ADR-007）。
四操作块的 round 01 是「归还先落地 → 借阅成功 → 删除被在借拦截」，
round 02 是「归还先落地 → 借阅撞已被借出 → 删除被拦」，
round 03 是「删除抢在借阅之前 → 借阅 404」——同一份代码、三种全序、全部自洽。

## 12. 已知边界

1. **交叉比对的采样点**：每轮四个并发请求全部返回后才读库与页面。断言对象是
   「并发结束后的系统自洽」，不是事务进行中的逐帧观测（后者需要 WAL 快照隔离下的外部读者，
   超出 v1 规模，NFR-2）。该窗口内测试进程不再发起写请求，读到的是稳定快照。
2. **四操作交叉实验每轮新建物品**：为了每轮都从确定起点出发，临时库里物品会随轮次增长
   （20 轮约 20 余件）。这是 tests/ 内的数据构造，不经过产品路径。
3. **并发日志写一次**：改「已存在则不覆盖」后，重复跑测试不再刷新证据；需要新证据时手动删文件。
4. **受限环境说明**：本机 DSH 沙箱下 Python 3.14 的 `os.mkdir(mode=0o700)` 会生成当前令牌
   不可列出的目录，导致 pytest `tmp_path` 失败；验证统一用 `testtmp/run_pytest.py` 启动器
   （在 `.gitignore` 内，非交付代码）。
5. **CSRF**：本故事未新增写端点，既有写路径的 CSRF 延期口径不变（PRD §6 明确不做）。
