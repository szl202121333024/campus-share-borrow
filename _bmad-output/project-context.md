---
title: 项目实现规约（Project Context）
status: final
created: 2026-11-08
updated: 2026-11-08
phase: 3 / bmad-create-epics-and-stories
upstream:
  - _bmad-output/planning-artifacts/prds/prd-campus-share-borrow-2026-11-08/prd.md
  - _bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/README.md
  - _bmad-output/planning-artifacts/epics.md
rules: 15
---

# 项目实现规约 · campus-share-borrow

**这份文件解决什么问题**：PRD 说「要什么」，ADR 说「为什么这么定」，本文件说「代码长什么样」。阶段 4 每写一个故事之前先读它，写完后按 §4 的自检清单逐条打勾。它不是建议，是**验收的一部分**——评审手册驳点 4-2 的判据就是「命名风格、目录结构跟 `project-context.md` 不一致」。

**共 15 条规约（PC-1 ~ PC-15）**，每条都给出「怎么判定」，能被 `grep`、`pytest` 或一条 SQL 检出，不依赖记忆。

---

## 1. 规约总表

| 编号 | 规约 | 一句话判据 | 依据 |
|---|---|---|---|
| **PC-1** | 目录与分层固定 | `app.py`/`db.py`/`services/`/`routes/`/`templates/`/`static/`/`tests/` 七项齐全；路由只收集参数与映射异常，业务判定全在 `services/`，模板不调用业务函数 | ADR-001 §5、ADR-001 §6 |
| **PC-2** | 数据库连接只有一个入口 | 全库 `sqlite3.connect(` 只命中 `db.py::get_db()` 一处；四项 PRAGMA 在 `get_db()` 内集中设置 | ADR-005 §2.1、§2.2 |
| **PC-3** | 命名一律 **snake_case** | 函数/变量/数据库列/模板变量/session 键均为 `snake_case`；类名 `PascalCase`；常量 `UPPER_SNAKE_CASE`；检索驼峰函数名 0 命中 | 评审手册驳点 4-2 |
| **PC-4** | 写路径只用 `BEGIN IMMEDIATE` | 检索 `BEGIN DEFERRED` 命中 0；写事务显式开启，不用 Python 隐式事务；事务内不渲染模板、不做哈希、不发网络请求 | ADR-002 §2.4、ADR-005 §2.2 |
| **PC-5** | 借阅 = 六步顺序 + 捕获 `IntegrityError` | ①未登录 302 → ②不存在 404 → ③停用 409 → ④本人已持有 409 → ⑤限额 409 → ⑥唯一约束 409；②③ 一次查询、④⑤ 一次聚合查询；⑥ 与 ④ 响应逐字一致 | PRD FR-3、D-006、D-008、D-016、ADR-002 §2.2 |
| **PC-6** | 归还只写 `loans` | 归还路径检索 `UPDATE items` 命中 0；条件 `UPDATE ... AND returned_at IS NULL` + `rowcount` 判定 | D-014、D-020、ADR-002 §2.3 |
| **PC-7** | 额度只有一处真相 | `get_remaining_quota(student_id)` 全库唯一，函数体内只有一条 SQL 聚合查询；页面换算只在模板层做一次 | D-013、PRD FR-5 |
| **PC-8** | 物品状态派生只有一处实现 | `list_items_with_state(...)` 全库唯一；`items.status` 只写 `available`/`unavailable`，检索 `'borrowed'` 写入 0 命中 | ADR-007 §2.1、§2.2、D-015 |
| **PC-9** | 业务失败返回真实 4xx + 错误码 | 错误码与中文文案各只有一处定义；禁止「200 + 错误文案」；写操作 POST + 302（PRG） | PRD §4 错误约定、ADR-001 §2 |
| **PC-10** | 无角色豁免 | 借阅与限额逻辑中不出现以角色为条件的分支；权限判断只在统一守卫里做一次 | D-012、PRD FR-5 |
| **PC-11** | 密码统一走一个函数，日志脱敏 | 只用 `generate_password_hash(method="pbkdf2:sha256")`；检索 `hashlib.md5`、`sha1` 命中 0；日志不含密码/哈希/cookie | ADR-004、ADR-005 §2.3 |
| **PC-12** | 依赖下限与无构建链 | `requirements.txt` 含 `Flask>=3.1.0`、`Werkzeug>=3.1.0`；仓库无 `package.json`/`vite.config.*`/`node_modules`/`dist` | ADR-001、ADR-005 §5.1 |
| **PC-13** | 测试命名与并发测试的硬要求 | `tests/test_*.py`、函数名 `test_*`；并发测试必须真并发（线程 + barrier + 独立连接）、跑 20 轮；白盒索引测试直接对 `loans` 执行 SQL | NFR-1、D-021、ADR-002 §4 |
| **PC-14** | 常量与时间格式 | `BORROW_LIMIT = 3`、`BORROW_DAYS = 7` 各只有一处定义；时间以 `YYYY-MM-DD HH:MM:SS` 文本存储，`due_at = borrowed_at + 7 天` | PRD §3 术语表、FR-3 |
| **PC-15** | 提交纪律 | 一个逻辑变更 = 一笔提交，前缀 `feat:`/`fix:`/`test:`/`docs:`；提交后立即 `push` | AGENTS.md §1、§1.1 |

---

## 2. 四条最容易写错的规约（展开说明）

### PC-2 · 连接入口与 PRAGMA（ADR-005）

```python
# db.py —— 全项目唯一允许出现 sqlite3.connect 的地方
import sqlite3
from flask import g

DB_PATH = "campus_share_borrow.sqlite"   # 仓库根目录，单文件

def get_db():
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH, isolation_level=None)  # 自动提交，事务边界自己管
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")      # 库级持久设置，幂等
        conn.execute("PRAGMA busy_timeout = 5000")     # 连接级：漏设会静默退回 0
        conn.execute("PRAGMA foreign_keys = ON")       # 连接级：漏设则外键失效
        conn.execute("PRAGMA synchronous = NORMAL")
        g.db = conn
    return g.db
```

- **为什么 `isolation_level=None`**：Python `sqlite3` 默认在 DML 前自动 `BEGIN`，且是 `DEFERRED` —— 直接违反 PC-4，且在并发测试里会以「偶发超卖」的形式暴露，排查成本极高。
- **必须断言 WAL 生效**：启动自举后执行 `PRAGMA journal_mode`，返回 `wal`（大小写不敏感）才继续；有活动事务时切换 WAL 会**静默失败**并返回原模式（ADR-005 §5.2）。
- **判据**：`grep -rn "sqlite3.connect" --include=*.py .` → 1 命中。

### PC-4 + PC-5 · 借阅写路径的骨架

```python
# services/borrow.py —— 六步顺序，整体包在 BEGIN IMMEDIATE 内
def borrow_item(student_id, item_id):
    db = get_db()
    db.execute("BEGIN IMMEDIATE")          # ① 先拿写锁，不是 DEFERRED
    try:
        row = db.execute(                  # ②③ 一次查询同时判存在与停用
            "SELECT id, status FROM items WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None:
            raise BizError(404, "RESOURCE_NOT_FOUND")
        if row["status"] == "unavailable":
            raise BizError(409, "ITEM_UNAVAILABLE")

        agg = db.execute(                  # ④⑤ 一次聚合同时算持有与额度
            "SELECT COUNT(*) AS total,"
            "       SUM(CASE WHEN item_id = ? THEN 1 ELSE 0 END) AS mine"
            "  FROM loans WHERE user_id = ? AND returned_at IS NULL",
            (item_id, student_id),
        ).fetchone()
        if agg["mine"] > 0:
            raise BizError(409, "ALREADY_BORROWED")     # ④
        if agg["total"] >= BORROW_LIMIT:
            raise BizError(409, "LIMIT_EXCEEDED")       # ⑤

        db.execute(                        # ⑥ 唯一索引在此兜底
            "INSERT INTO loans (item_id, user_id, borrowed_at, due_at)"
            " VALUES (?, ?, ?, ?)",
            (item_id, student_id, now_text(), due_text()),  # due = borrowed + 7 天
        )
        db.execute("COMMIT")
    except sqlite3.IntegrityError as exc:
        db.execute("ROLLBACK")
        if "loans.item_id" not in str(exc):     # 只认唯一约束，别把外键错误伪装成 409
            raise
        raise BizError(409, "ALREADY_BORROWED")  # 与 ④ 完全一致的响应
    except BaseException:
        db.execute("ROLLBACK")
        raise
```

- **④ 必须在 ⑤ 之前**：双击场景的第二个请求要落在 ④，才能返回与 ⑥ 一致的文案（D-016）。
- **`IntegrityError` 精确捕获**：`except Exception` 会把真实 bug 伪装成业务冲突，属评审红线（ADR-002 §4）。

### PC-6 · 归还：条件 UPDATE + `rowcount`

```python
# services/return_loan.py
cur = db.execute(
    "UPDATE loans SET returned_at = ?"
    " WHERE id = ? AND user_id = ? AND returned_at IS NULL",
    (now_text(), loan_id, student_id),
)
if cur.rowcount == 1:
    db.execute("COMMIT")            # 成功；额度自动释放，无需另写
else:
    row = db.execute("SELECT user_id, returned_at FROM loans WHERE id = ?",
                     (loan_id,)).fetchone()
    if row is None or row["user_id"] != student_id:
        raise BizError(404, "RESOURCE_NOT_FOUND")   # 不存在与非本人：同一响应（D-011）
    raise BizError(409, "ALREADY_RETURNED")
```

- **绝不出现** `UPDATE items` —— 「停用物品归还后仍停用」「未停用物品归还后回到可借」这两个行为由派生查询自动成立，不需要任何 `if`（ADR-007 §2.3）。

### PC-7 + PC-8 · 两处「唯一真相」

```python
# services/quota.py —— 额度唯一真相，只含一条聚合查询
def get_remaining_quota(student_id):
    row = get_db().execute(
        "SELECT COUNT(*) AS held FROM loans"
        " WHERE user_id = ? AND returned_at IS NULL", (student_id,)
    ).fetchone()
    return BORROW_LIMIT - row["held"]        # 返回「剩余」，页面显示 X = 3 - 剩余
```

```python
# services/items.py —— 物品 + 在借状态的唯一派生实现
def list_items_with_state(query=None, include_unavailable=False):
    # 一次查询取全量：状态、应还日期、借阅人姓名；禁止对每条物品单独再查（N+1）
    ...
```

- 列表页、搜索页、管理页**全部**复用 `list_items_with_state`；展示优先级 `unavailable > borrowed > available` 只在一个函数里比较，模板只渲染（ADR-007 §2.2）。
- 判据：`grep -rn "returned_at IS NULL" services/` → 只出现在 `quota.py`、`items.py`、`borrow.py`、`return_loan.py` 四处；不存在第五处重复实现。

---

## 3. 目录结构与命名样例

```
campus-share-borrow/
├── app.py                 # 唯一入口：python app.py → 自举 + 起服务（PC-1、PC-12）
├── db.py                  # get_db()、建表、种子数据（PC-2）
├── config.py              # BORROW_LIMIT / BORROW_DAYS / 错误码常量（PC-9、PC-14）
├── security.py            # 密码哈希唯一入口（PC-11）
├── routes/                # 蓝图：auth / items / loans / admin（只收集参数 + 映射异常）
├── services/              # 业务判定：borrow / return_loan / quota / items / admin
├── templates/             # Jinja2，服务端渲染，无前端构建链（PC-12）
├── static/                # 一个 css 文件即可，不引 CDN 框架
├── tests/                 # pytest：test_auth.py / test_items.py / test_borrow.py
│                          #        test_return.py / test_admin.py / test_concurrency.py
├── requirements.txt       # Flask>=3.1.0 / Werkzeug>=3.1.0 / pytest
└── README.md              # 唯一启动命令 + 种子账号 + 已知限制
```

**命名对照（PC-3）**

| 位置 | 正确 | 错误 |
|---|---|---|
| 函数 | `borrow_item()`、`get_remaining_quota()` | `borrowBook()`、`getRemainingQuota()` |
| 变量 | `item_id`、`student_id`、`due_at` | `itemId`、`studentID`、`dueDate` |
| 数据库列 | `returned_at`、`borrowed_at` | `returnedAt`、`BorrowedAt` |
| 模板变量 | `{{ remaining_quota }}`、`{{ loan_list }}` | `{{ remainingQuota }}` |
| 常量 | `BORROW_LIMIT`、`MAX_NAME_LEN` | `borrowLimit`、`maxNameLen` |
| 类 | `BizError` | `biz_error` |

---

## 4. 每个故事的完成自检清单（DoD）

写完一个故事后逐条打勾，缺一条不算完成：

- [ ] **PC-1** 新代码落在 `services/` 或 `routes/`，没有把业务判定写进路由函数或模板
- [ ] **PC-2** 没有新增 `sqlite3.connect(`；新连接都走 `get_db()`
- [ ] **PC-3** 新增标识符全为 `snake_case`（`grep -nE "[a-z]+[A-Z][a-zA-Z]*\(" --include=*.py .` 应 0 命中）
- [ ] **PC-4** 新增写路径以 `BEGIN IMMEDIATE` 开启；`grep -c "BEGIN DEFERRED"` 为 0
- [ ] **PC-5** 若触碰借阅：六步顺序未被重排，`IntegrityError` 精确捕获
- [ ] **PC-6** 若触碰归还：`grep -n "UPDATE items" services/` 未新增命中
- [ ] **PC-7** 额度仍只有 `get_remaining_quota` 一处实现
- [ ] **PC-8** 物品状态仍只有 `list_items_with_state` 一处派生实现；未写入 `'borrowed'`
- [ ] **PC-9** 失败返回真实 4xx + 已定义错误码；中文文案与错误码常量同源
- [ ] **PC-10** 未引入 `if role != 'admin'` 之类的限额分支
- [ ] **PC-11** 未打印密码/哈希/cookie；密码只经 `security.py`
- [ ] **PC-13** 新测试文件与函数按 `test_*` 命名；若涉及并发，真并发 + 20 轮
- [ ] **PC-15** 已 `git add` 本次文件 → `commit`（前缀合规）→ `push`

---

## 5. 明确禁止的写法（出现即返工）

| 禁止 | 为什么 | 替代 |
|---|---|---|
| 先 `SELECT` 判可借/判额度，再据此 `INSERT` 当唯一裁决 | TOCTOU；命中 PRD §8.4 否决项 B | 唯一索引兜底 + `BEGIN IMMEDIATE`（PC-4、PC-5） |
| `BEGIN DEFERRED`、或依赖 Python 隐式事务 | 延迟事务在并发下不保证额度原子 | 显式 `BEGIN IMMEDIATE` |
| `UPDATE items SET status = 'borrowed'` | 违反 ADR-007 单写入者；`CHECK` 也会拒绝 | 「在借」由 `loans` 派生（PC-8） |
| 归还里顺手 `UPDATE items SET status='available'` | 会让停用物品悄悄上架（D-005 的坑） | 归还只写 `loans`（PC-6） |
| `items` 表加 `quantity` / `stock` 列 | 一物一行是本项目不变量成立的前提（ADR-006） | 同款多件录多条 |
| 用 `except Exception` 把所有异常映射成 409 | 真实 bug 被伪装成业务冲突 | 只捕获唯一约束冲突（PC-5） |
| 返回 200 + `{"error": "..."}` | 测试无法断言，违反 PRD §4 错误约定 | 真实 4xx + 错误码（PC-9） |
| 引入 `package.json` / vite / React | 违反 ADR-001 与 NFR-2 | Jinja2 服务端渲染（PC-12） |
| `hashlib.md5` / 明文 / 自写加盐 | 违反 ADR-004 | `generate_password_hash(method="pbkdf2:sha256")` |
| 在事务里渲染模板或做哈希 | 拉长持锁时间，`busy_timeout` 会被耗尽 | 事务内只做数据库操作（PC-4） |

---

## 6. 变更流程

- 任何一条规约的修改都必须先改**本文件**并说明理由，再改代码；不允许「代码先飘、规约后补」。
- 规约与 ADR 冲突时，**ADR 优先**，并把冲突记入 `decision-log.md` 交人类裁决。
- 新增规约时同步更新 §1 总表的编号与 `rules:` 计数（当前 **15** 条）。

*文档结束。下游：阶段 4 `bmad-sprint-planning` → `bmad-build`，逐故事实施，每个故事按 §4 自检。*
