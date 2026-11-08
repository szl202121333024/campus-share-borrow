---
id: ADR-002
title: 并发唯一性——部分唯一索引 + 立即写事务
status: accepted
created: 2026-11-08
updated: 2026-11-08
deciders: [架构评审人（人类）, AI 架构师]
decision_log: [D-009, D-018]
related: [FR-3, FR-4, FR-5, NFR-1]
---

# ADR-002 · 并发唯一性：部分唯一索引 + `BEGIN IMMEDIATE` 写事务

**决定：两条并发不变量分别交给两个不同的机制——物品唯一性由「`item_id` 上的部分唯一索引」物理兜底；用户额度由「`BEGIN IMMEDIATE` 写事务」保证原子。两者分工明确，缺一不可。代码捕获 `IntegrityError` 后返回 409 `ALREADY_BORROWED`。**

**否决的备选：仅靠应用层 `SELECT` 检查（先查后写）；或单纯用写锁代替唯一索引充当唯一性裁决者。**

## 1. 背景

NFR-1 是本项目唯一的技术难点，它其实是**两条独立的不变量**，容易被当成一条处理：

| 不变量 | 含义 | 破坏后的表现 | 对应验收 |
|---|---|---|---|
| **物品唯一性** | 同一物品同时最多存在 1 条未归还记录 | 超卖：两人都借走同一件 | NFR-1.1 |
| **用户额度** | 同一用户未归还记录数 ≤ 3 | 越限：同时借两件，额度从 2 变 4 | NFR-1.2 |

AI 架构师的初始建议是经典写法：借阅时先 `SELECT` 该物品是否有未归还记录，确认可借再 `INSERT`/`UPDATE`；额度同理，先 `COUNT` 再插入。该建议被否决（D-009），并在评审中被人类进一步加严为「两条不变量必须各有一个数据库级机制」。

**问题的本质是 TOCTOU（检查与使用之间存在时间窗）**：两个请求在检查阶段都看不到对方的写入，于是都通过检查、都执行写入。这个窗口在任何「先查后写」的实现里必然存在，靠缩短窗口无法消除，只能让**写入本身具备拒绝能力**。

## 2. 决定

### 2.1 数据层：让数据库持有不变量

```sql
CREATE TABLE items (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT    NOT NULL,
  category   TEXT    NOT NULL CHECK (category IN ('book','equipment')),
  status     TEXT    NOT NULL DEFAULT 'available'
                     CHECK (status IN ('available','unavailable')),
  created_at TEXT    NOT NULL
);

CREATE TABLE loans (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id     INTEGER NOT NULL REFERENCES items(id),   -- 不用 ON DELETE CASCADE
  user_id     INTEGER NOT NULL REFERENCES users(id),
  borrowed_at TEXT    NOT NULL,
  due_at      TEXT    NOT NULL,
  returned_at TEXT                                       -- NULL 即在借
);

-- 唯一性裁决者：同一物品同时最多 1 条未归还记录
CREATE UNIQUE INDEX ux_loans_active_item
  ON loans(item_id)
  WHERE returned_at IS NULL;
```

- **部分唯一索引只作用于未归还记录**（`WHERE returned_at IS NULL`），因此「归还后可以再借同一件」自动成立，不需要任何额外清理。
- `items.status` 的 `CHECK` 约束把 ADR-007「不存 `borrowed`」这条规则落到物理层，任何写入 `borrowed` 的代码会直接报错。
- **`item_id` 外键刻意不用 `ON DELETE CASCADE`**：级联删除会静默删掉在借记录，从而掩盖 FR-6「有未归记录禁止删除」的漏判。改为在删除事务内显式 `DELETE FROM loans WHERE item_id=? AND returned_at IS NOT NULL`，若仍有在借记录则外键直接报错——**错误要响，不要静默**。

### 2.2 借阅的判定顺序（与 PRD FR-3 的六步一一对应）

全部在**同一个 `BEGIN IMMEDIATE` 事务内**完成：

| 序 | 判定 | 实现要点 | 结果 |
|---|---|---|---|
| ① | 未登录 | 会话中无 `user_id` | 302 → `/login?next=` |
| ② | 物品不存在 | 与 ③ **同一条** `SELECT id, status FROM items WHERE id=?` | 404 `RESOURCE_NOT_FOUND` |
| ③ | 物品已停用 | 同上，读同一行的 `status` | 409 `ITEM_UNAVAILABLE` |
| ④ | 本人已持有该物品 | 与 ⑤ **同一条**聚合查询 | 409 `ALREADY_BORROWED` |
| ⑤ | 已达限额 3 件 | 同上（同一查询同时算出总额度） | 409 `LIMIT_EXCEEDED` |
| ⑥ | 唯一索引冲突 | 捕获 `sqlite3.IntegrityError` | 409 `ALREADY_BORROWED` |

- ②③ 合并为一次查询（D-008）：两次查询之间状态可能改变，判定结果不自洽。
- ④⑤ 合并为一次聚合查询（D-016）：双击场景第二个请求必须落在 ④，才能返回与 ⑥ 完全一致的文案；同时不增加查询次数。
- **⑥ 的响应与 ④ 完全一致**（同状态码、同错误码、同文案），两条拦截路径对用户不可区分——这是 PRD FR-3 的硬要求，也是唯一索引能在不影响 UX 的前提下兜底的前提。

### 2.3 归还的原子收尾

归还用一个**条件 UPDATE**（CAS 语义）实现，而不是「先查状态再更新」：

```
UPDATE loans SET returned_at = :now
 WHERE id = :loan_id AND user_id = :me AND returned_at IS NULL
```

- `rowcount == 1` → 归还成功，额度自动释放（额度是派生的，无需另写）。
- `rowcount == 0` → 再用一次 `SELECT` 区分：记录存在且已归还 → 409 `ALREADY_RETURNED`；不存在或非本人 → 404 `RESOURCE_NOT_FOUND`（D-011：两种原因同一响应）。
- 并发归还同一记录时，只有第一个 `UPDATE` 能拿到 `rowcount == 1`，天然满足 NFR-1.3「`returned_at` 只被写入一次」。

### 2.4 硬性禁令（可被静态检查）

- 禁止 `BEGIN DEFERRED`；写路径一律 `BEGIN IMMEDIATE`。
- 禁止在事务外做额度计数；额度校验与 `INSERT` 必须同事务（D-009）。
- 禁止「先 `SELECT` 查可借/查额度，再据此 `INSERT` 并作为唯一裁决」——唯一裁决者必须是 ⑤ 的事务原子性 + ⑥ 的索引。

## 3. 否决的备选方案

### 3.1 备选一：应用层「先 SELECT 再 UPDATE/INSERT」（初始建议，被否决）

**否决理由**：这是 TOCTOU 的教科书案例。两个并发请求在检查阶段都读到「可借」，都进入写入分支，结果是 2 条在借记录 = 超卖，直接违反 NFR-1.1，并命中 PRD §8.4 的**否决项 B**（用先查后写且无兜底）。补充说明：靠「检查后立刻写入、窗口极短」来自我安慰无效——并发测试跑 20 轮必然命中，概率不是防线。

### 3.2 备选二：单纯用写锁充当唯一性裁决者

**方案**：给借阅动作加悲观锁（应用层互斥 / 表级写锁 / 全局 `threading.Lock`），靠「同一时刻只有一个借阅在执行」来防重复。

**否决理由**：**锁是并发控制手段，不是不变量的表达**。① 锁保护的是「代码路径」，一旦有人新写一条绕开该路径的插入（脚本、种子导入、将来的管理端功能），不变量立刻失效，而数据库不会拦；② 锁的作用域写错（加锁粒度、提前提交、异常路径未释放）是静默失效，测试不测就发现不了；③ 本项目的部署形态被 ADR-005 固定为单进程，应用层锁才「碰巧有效」——正确性依赖部署形态，是脆弱的；④ 唯一索引在**数据层面**证明「最多 1 条」，即使应用逻辑有 bug 也拦得住，这是物理底线的最后一道闸。

**关键澄清（避免被读成「否决写事务」）**：本 ADR **保留并强制** `BEGIN IMMEDIATE` 写事务，但它承担的是**另一条不变量**——额度（COUNT 与 INSERT 的原子性）。被否决的是「用锁去代替唯一索引当物品唯一性的裁决者」，不是「用事务」。

### 3.3 备选三：`UNIQUE(user_id, item_id)`（非部分索引）

**否决理由**：两处错误。① **防不住超卖**——它只约束「同一人不能对同一物品有两条记录」，两个**不同**用户仍可同时各借一条，NFR-1.1 直接不成立；② **不带 `WHERE` 会永久占用组合键**——归还后的历史记录仍在索引里，该用户此后再也无法借同一件，与 FR-3「归还后可再借」正面冲突。（此错误源自评审手册初稿的笔误，已在 D-018 中确认并修正。）

### 3.4 备选四：把「在借」写成 `items.status = 'borrowed'` 并由它裁决唯一性

**否决理由**：违反 ADR-007 的单写入者约束。`borrowed` 一旦成为存储值，归还就必须同时改两张表，且「停用」与「在借」无法共存（一件物品同时在借又被停用时，单值列表达不了两个事实）；这正是 D-005 隐患的来源。

### 3.5 备选五：额度校验放在事务外，或分两个事务

**否决理由**：两名各差一件满额的用户并发借阅两件不同物品时，两个事务各自的 `COUNT` 都读到 2，都判定未满额，最终在借数变 4——NFR-1.2 失败。额度不变量只能靠「计数与插入在同一把写锁内」保证，而 SQLite 的写锁就是 `BEGIN IMMEDIATE`（D-009）。

## 4. 后果

**正面**

- 不变量由数据库持有：最坏情况仍是「该物品在借记录恰好 1 条」，任何应用层 bug 都不能突破它。
- **测试与机制一一对应**，不会「测了一个、漏了另一个」：
  - NFR-1.1（物品唯一性）→ 部分唯一索引 + 并发 20 轮；
  - NFR-1.2（额度）→ `BEGIN IMMEDIATE`；
  - NFR-1.3（并发归还）→ 条件 `UPDATE` 的 `rowcount`。
- 归还路径不需要「释放额度」的代码，额度天然派生，消除一类遗漏。

**负面 / 代价**

- **⑥ 在正常路径下几乎不会被触发**：因为 ④ 已在同一事务内拦下重复借阅，唯一索引只在「应用层判定被绕过」时才生效。**这意味着「建了索引」这件事无法被黑盒并发测试证明**。因此必须补两个测试：① 两用户并发借同一件（NFR-1.1，真正考验索引）；② 直接对 `loans` 执行一条绕过服务层的 `INSERT`，断言抛 `IntegrityError`——后者才是索引存在的直接证据。
- **写操作被串行化**：`BEGIN IMMEDIATE` 会在事务开始即取写锁，所有写请求排队。50 条物品、单班规模下无影响，但**事务内不得有耗时操作**（渲染、网络、哈希计算），否则 `busy_timeout` 可能被耗尽（ADR-005）。
- **部分索引要求 SQLite ≥ 3.8.0**：本机实测 `sqlite3 3.50.4`，满足。
- **删除物品必须与级联清理同事务**：`DELETE loans` + `DELETE items` 两语句在一个 `BEGIN IMMEDIATE` 内，否则会出现「物品删了、历史还在」的中间态（FR-6、D-010）。
- **`IntegrityError` 必须被精确捕获**：只捕获唯一约束冲突，不能用一个 `except Exception` 把其他约束错误也映射成 409，否则真实 bug 会被伪装成业务冲突。

## 5. 下游含义（供阶段 3/4 引用）

- `project-context.md` 必须固化：「借阅写路径整体包在 `BEGIN IMMEDIATE` 中，先校验后插入，捕获 `IntegrityError` 映射 409」（D-009）。
- 并发测试必须同时覆盖 NFR-1.1 与 NFR-1.2，且**不得合并为一个用例**（PRD NFR-1.2 明确要求独立成故事）。
- 任何「加锁代替索引」的实现方式，按 PRD §8.4 否决项 B 判定为项目核心失败。
