---
title: 史诗与故事分解
status: final
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-campus-share-borrow-2026-11-08/prd.md
  - _bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/README.md
  - _bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/ADR-001-rendering.md
  - _bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/ADR-002-concurrency-uniqueness.md
  - _bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/ADR-003-session.md
  - _bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/ADR-004-password-storage.md
  - _bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/ADR-005-concurrency-deployment.md
  - _bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/ADR-006-item-model.md
  - _bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/ADR-007-item-state-machine.md
  - decision-log.md
  - docs/review-playbook.md
  - docs/assignment-brief.md
created: 2026-11-08
updated: 2026-11-08
phase: 3 / bmad-create-epics-and-stories
epics: 3
stories: 12
---

# 校园共享器材 / 图书借阅系统 - Epic Breakdown

本文把 PRD（`status: final`）的 6 条功能需求、2 条非功能需求，连同 7 条 ADR 给出的技术约束，分解为 **3 个史诗 / 12 个故事**。每个故事都能被一个开发会话独立完成，每条验收标准都能被一条自动化测试或一段可复述的手工步骤判定。

## 0. 范围守门（Scope Gate）

> 这一节不是故事，是**对本文件自身的约束**。它先于任何故事生效。

**上限已锁死：3 个史诗 / 12 个故事。** 依据三条，缺一条都不足以支撑这个上限：

| 依据 | 出处 | 含义 |
|---|---|---|
| 工期 | PRD §8.3 SM-C1 | 「故事数达标（≥12）即可，多出来的功能一律按超范围驳回」；堆功能会直接吃掉并发测试的时间预算 |
| 评审标准 | `docs/review-playbook.md` 驳点 3-1 | 故事一旦引入 PRD 非目标，即按超范围驳回 |
| 人类裁决 | `decision-log.md` D-022 | 本阶段启动时人类下达「本迭代只有 3 个史诗 / 12 个故事」的硬约束 |

**变更规则**：任何新增故事必须先在 `decision-log.md` 记一条决策并由人类裁决；未记决策的新增故事一律驳回，理由固定为「12 个故事够用了，多了会导致工期失控」。

**本迭代对 PRD §6「明确不做」的九类非目标零故事覆盖**：评论 / 图片上传 / 跨班共享 / 逾期罚款与催还 / 强制删除在借物品 / 借阅历史视图 / 注册改密与登录锁定 / 管理员代还与批量操作与审计日志 / 前后端分离。上述内容不出现在任何一个故事正文里；`§6 Reviewer Gate 自检` 的 A-6 项给出脚本化核验结果。

**已识别的边缘故事（提出后主动删除，不进入本迭代）**：

| 曾被考虑的拆分 | 删除理由 |
|---|---|
| 「物品详情页」 | PRD FR-2 Out of Scope 明确不做；列表即全部展示信息 |
| 「借阅历史视图」 | PRD §6 明确不做（连带不做快照字段，D-007） |
| 「搜索分页与排序」 | PRD FR-2 Out of Scope；单班上限 50 条（A-1） |
| 「管理员编辑物品名称」 | PRD FR-6 Out of Scope，且与 ADR-007「名称单一真相」冲突 |
| 「操作审计日志」 | PRD FR-6 Out of Scope |
| 「并发归还」独立成故事 | NFR-1.3 的验收并入 Story 2.2 的 AC-2.2.9，独立成故事会与 2.3/2.4 重复同一套并发脚手架 |

**保留的 12 个故事构成**：

| 史诗 | 故事数 | 故事编号 |
|---|---|---|
| Epic 1 认证与浏览 | 3 | 1.1、1.2、1.3 |
| Epic 2 借阅、归还与并发一致性 | 5 | 2.1、2.2、2.3、2.4、2.5 |
| Epic 3 管理员维护物品清单 | 4 | 3.1、3.2、3.3、3.4 |

---

## 1. Requirements Inventory

### 1.1 Functional Requirements

FR 编号与 PRD 一一对应，措辞压缩为可验收的一句话；完整 Consequences 见 PRD §4。

- **FR-1 学号登录、会话与访问控制**：学生与管理员用「学号 + 密码」登录，会话承载身份；未登录访问受保护路径 → 302 到 `/login?next=`；学生访问 `/admin/*` → 403；密码不落明文。（PRD §4.1，realizes UJ-1）
- **FR-2 物品列表与关键字搜索**：`GET /items` 匿名可读，列出全部非停用物品（先 `book` 后 `equipment`，组内按名称升序）；`?q=` 按名称包含匹配（忽略大小写与首尾空白，`%`/`_` 作普通字符）；无匹配返回 200 + 空状态；每条展示名称/类别/状态，在借时展示应还日期；访客不见借阅人姓名，学号永不出现。（PRD §4.2，realizes UJ-1、UJ-4）
- **FR-3 借阅物品**：登录用户对可借物品 `POST /borrow` 成功 → 302 + 应还日期 = 借出时间 + 7 天；失败按**固定六步顺序**返回 302/404/409 与对应错误码；失败无副作用；额度校验与写入同事务。（PRD §4.3，realizes UJ-1、UJ-4）
- **FR-4 归还物品**：本人对自己的在借记录 `POST /return/<loan_id>` → 写入 `returned_at`、额度即时释放；重复归还 409 `ALREADY_RETURNED`；他人记录与不存在均 404 `RESOURCE_NOT_FOUND` 且响应完全一致；归还只写 `loans`，不得改 `items.status`。（PRD §4.4，realizes UJ-2）
- **FR-5 借阅限额 3 件**：每个用户同时在借 ≤ 3 件；超限 409 `LIMIT_EXCEEDED`；计数只算 `returned_at IS NULL`；逾期记录计入额度但不构成拦截；额度只有一处真相 `get_remaining_quota(student_id)`；管理员无豁免。（PRD §4.5，realizes UJ-2）
- **FR-6 管理员维护物品清单**：新增（名称 1–50 字符、类别枚举、默认 `available`）、删除（有在借 409 `ITEM_IN_BORROW`；否则同事务级联清理已归还记录）、停用（任何状态可停用、幂等）、恢复上架（幂等）；越权 403 `FORBIDDEN`；管理列表含停用项与在借人。（PRD §4.6，realizes UJ-3）

### 1.2 Non-Functional Requirements

- **NFR-1 并发一致性**（本项目唯一技术难点，5 条断言 + 3 条禁令，逐条对应故事）：
  - **NFR-1.1 同一物品并发借阅**：两线程同时借同一件 → 状态码集合**恰好** `{302, 409}`，失败方 `ALREADY_BORROWED`，该 `item_id` 未归还记录**恰好 1 条**；连续 20 轮不例外。→ **独立故事 2.3**（考数据库部分唯一索引）。
  - **NFR-1.2 同一用户并发超额**：用户在借 2 件时并发借 2 件不同物品 → **恰好 1 成功、1 `LIMIT_EXCEEDED`**，在借数最终**恰好 3**；连续 20 轮不出现 4。→ **独立故事 2.4**（考 `BEGIN IMMEDIATE` 写事务）。**PRD 明文要求 1.1 与 1.2 不得合并成一个故事。**
  - **NFR-1.3 并发归还**：同一 `loan_id` 并发归还两次 → 恰好 1 成功、1 `ALREADY_RETURNED`，`returned_at` 只写一次。→ Story 2.2。
  - **NFR-1.4 无中间态**：并发结束后不存在「有在借记录但显示可借」或反之。→ Story 2.3、3.4。
  - **NFR-1.5 失败无副作用**：任一失败请求后 `loans` 行数与 `items.status` 与请求前逐字段一致。→ Story 2.1、2.3、2.4。
  - **禁令**：禁止「先 `SELECT` 判可借/判额度、再 `INSERT`」作为唯一裁决；禁止 `BEGIN DEFERRED`；额度校验与插入不得分处两事务。
- **NFR-2 可运维性**：干净环境按 README 声明的**唯一命令**一次执行即成功（断言对象是「命令一次执行即成功」）；首次启动自举建表 + 种子数据；单文件 `.sqlite` 存储；冷启动 < 10 秒；无前端构建产物；单进程即可；失败可诊断（非零退出 + 一行可读原因）。→ Story 1.1。

### 1.3 Additional Requirements（来自架构，非 PRD 原文）

AR 编号供故事引用；每条都来自已定稿的 ADR，不再是待议项。

- **AR-1 借阅写路径整体包在 `BEGIN IMMEDIATE` 内**：先按六步顺序校验 → 再 `INSERT` → 捕获 `IntegrityError` 映射 409；禁 `BEGIN DEFERRED`。（ADR-002 §2.2、§2.4）
- **AR-2 唯一索引的存在性必须被直测**：除黑盒并发测试外，必须有「绕过服务层直接 `INSERT`，断言抛 `IntegrityError`」的测试 —— 因为 ④ 已在其前面拦截，正常路径下索引几乎不可达。（ADR-002 §4、D-021、架构索引 §3 第 2 条）
- **AR-3 归还只能写 `loans`**：`UPDATE loans SET returned_at=? WHERE id=? AND user_id=? AND returned_at IS NULL`，用 `rowcount` 判成败。（ADR-002 §2.3、D-020）
- **AR-4 物品状态永不存 `borrowed`**：`items.status` 只有 `available`/`unavailable`，由 `CHECK` 约束兜底；`borrowed` 由 `loans` 派生。（ADR-007 §2.1）
- **AR-5 派生查询与额度查询各自唯一**：`list_items_with_state(...)` 是「物品 + 在借状态」的唯一实现；`get_remaining_quota(student_id)` 只含一条 SQL 聚合查询，前置校验与页面指示共用。（ADR-007 §2.2、D-013）
- **AR-6 连接只有一处入口**：所有连接经 `get_db()`；四项 PRAGMA（`journal_mode=WAL`、`busy_timeout=5000`、`foreign_keys=ON`、`synchronous=NORMAL`）在 `get_db()` 内集中设置，禁止直接 `sqlite3.connect()`。（ADR-005 §2.1、§2.2）
- **AR-7 启动自举必须断言 `PRAGMA journal_mode` 返回 `wal`**，否则静默退化。（ADR-005 §5.2）
- **AR-8 密码统一走一个函数**：`generate_password_hash(method="pbkdf2:sha256")`，禁手写哈希、禁 `hashlib.md5`、禁日志打印密码/哈希/完整 cookie；学号不存在时也执行一次哈希校验。（ADR-004）
- **AR-9 无前端构建链、单进程一条命令**：仓库不得出现 `package.json` / `vite.config.*` / `node_modules` / `dist`；`Flask>=3.1.0` + `Werkzeug>=3.1.0` 是硬性下限。（ADR-001、ADR-005 §5.1）
- **AR-10 错误码与中文文案只有一处真相**：服务层抛业务异常 → 统一错误处理器映射状态码 + 渲染提示；业务失败返回真实 4xx，禁止「200 + 错误文案」；写操作 POST + 302（PRG）。（ADR-001 §2、PRD §4 错误约定）
- **AR-11 所有角色统一业务规则**：无 `if role != 'admin'` 的限额分支。（D-012）

### 1.4 UX Design Requirements

**本阶段无 UX 设计稿输入**，故无 UX-DR 项：PRD §8.3 SM-C3 明确「界面美观度不优化，只要求信息可读、状态可见」，作业也未要求 `bmad-ux` 产物。最低可读性要求（状态文案、错误提示、限额指示、空状态）已直接写入相关故事的验收标准，不另立史诗。

### 1.5 FR Coverage Map

| 需求 | 史诗 | 覆盖故事 | 覆盖要点 |
|---|---|---|---|
| FR-1 | Epic 1 | 1.2 | 登录/登出/会话/403/302 拦截/密码哈希 |
| FR-2 | Epic 1 | 1.3 | 列表排序、搜索转义、空状态、借阅人可见性、`no-store` |
| FR-3 | Epic 2 | 2.1、2.5 | 借阅成功与六步错误判定；`/my-loans` 只列在借 |
| FR-4 | Epic 2 | 2.2 | 归还、重复归还、越权/不存在、停用物品归还保持停用 |
| FR-5 | Epic 2 | 2.1、2.4、2.5 | 超限拒绝、并发不越限、限额指示与单一额度函数 |
| FR-6 | Epic 3 | 3.1、3.2、3.3、3.4 | 新增、删除（含级联）、停用、恢复上架 |
| NFR-1.1 | Epic 2 | 2.3 | 部分唯一索引 + 20 轮并发 + D-021 白盒直测 |
| NFR-1.2 | Epic 2 | 2.4 | `BEGIN IMMEDIATE` + 20 轮并发 + D-021 白盒直测（**与 2.3 独立**） |
| NFR-1.3 | Epic 2 | 2.2 | 条件 `UPDATE` + `rowcount`，并发归还只成功一次 |
| NFR-1.4 | Epic 2 / 3 | 2.3、3.4 | 派生态一致性交叉验证 |
| NFR-1.5 | Epic 2 | 2.1、2.3、2.4 | 失败逐字段无副作用 |
| NFR-2 | Epic 1 | 1.1 | 一条命令、自举、单文件、WAL 断言、无构建链 |

**覆盖率：FR 6/6，NFR 全条目（1.1~1.5、2）均有故事承载，无遗漏项。**

---

## 2. 史诗一览（Epic List）

### Epic 1：认证与浏览 —— 先让人看得见，再让人被认出

**目标**：任何人打开浏览器（不含登录）就能看到「班里有哪 6 件东西、哪些现在在别人手上、什么时候还」，并在需要时用学号证明自己是谁；同时把「一条命令启动 + 自带演示数据」这条运维底线一次做对，让后续所有故事都跑在同一个可复现环境上。

**覆盖**：FR-1、FR-2、NFR-2（+ AR-6、AR-7、AR-8、AR-9、AR-10）
**用户价值**：UJ-1 的前半段（搜索 → 看见状态）独立可用；评审人在干净机器上一条命令就能验证。

### Epic 2：借阅、归还与并发一致性 —— 一件东西只能在一个人的手上

**目标**：把「借」和「还」这条写热点做对：成功路径给出明确的应还日期，失败路径给出六种可区分的理由；并在数据库层面证明「两个人同时点借阅，只有一个人成功」「同一个人同时借两件，不会借出第 4 件」。本史诗是 NFR-1 的唯一落点，两个并发不变量各自拥有独立故事与独立验收。

**覆盖**：FR-3、FR-4、FR-5、NFR-1.1~NFR-1.5（+ AR-1、AR-2、AR-3、AR-4、AR-5）
**用户价值**：UJ-1、UJ-2、UJ-4 全部可用；SM-1 的 5 步脚本闭合成环。

### Epic 3：管理员维护物品清单 —— 清单跟着现实变

**目标**：让清单在「新增一件、坏了下架、修好上架、彻底删除」四种现实变化下都有确定结果，且任何时刻都有下一步可走（不会撞上「既不能删也不能下架」的死角）；同时用可 `grep` 的方式守住「物品状态只有管理员能改」这条结构约束。

**覆盖**：FR-6（+ AR-4、AR-5、AR-10、AR-11）
**用户价值**：UJ-3 可用；SM-4「管理动作无死角」可演示。

**史诗独立性**：Epic 1 单独可用（浏览 + 登录）；Epic 2 只依赖 Epic 1（登录态与列表页）；Epic 3 只依赖 Epic 1（管理员登录、`items`/`loans` 表结构），**不依赖 Epic 2 的借阅/归还功能**——Epic 3 的测试需要「有在借记录」时，用 SQL 直接构造，不调用借阅接口。

---

## 3. Epic 1：认证与浏览

**目标**：一条命令起得来、有东西可看、有人可登录。
**覆盖**：FR-1、FR-2、NFR-2。**故事数：3。**
**Epic 完成定义**：在干净机器上 `python app.py` 一次成功 → 匿名可读列表与搜索 → 学生登录后身份可见 → 学生访问 `/admin/items` 得 403。

### Story 1.1：一条命令启动、自动建表与种子数据

作为**演示者（评审人）**，
我希望 在干净机器上执行 README 声明的唯一命令，就得到可访问、自带演示数据的系统，
以便 评审不需要准备环境、不需要手工准备数据（NFR-2、SM-3）。

**关联**：NFR-2、AR-6、AR-7、AR-9、ADR-005、ADR-002 §2.1、D-018
**依赖**：无（本史诗第一个故事，也是全项目第一个故事）
**规模**：单次开发会话可完成（建库脚本 + 种子数据 + 启动入口 + README 命令段）

**验收标准：**

**AC-1.1.1**
**Given** 干净机器、已执行 `pip install -r requirements.txt`、仓库根目录下不存在 `.sqlite` 文件
**When** 执行 README 中声明的唯一启动命令 `python app.py`
**Then** 进程在 **10 秒内**开始监听 README 声明的地址，且 `GET /items` 返回 **200**
**And** 全过程不需要第二个进程、不需要执行迁移脚本、不需要手工建库

**AC-1.1.2**
**Given** 数据库文件不存在
**When** 启动完成
**Then** `users`、`items`、`loans` 三张表已存在
**And** 已写入种子数据：**2 个学生账号、1 个管理员账号、6 件物品（3 件 `book` + 3 件 `equipment`）**
**And** `GET /items` 能列出这 6 件物品

**AC-1.1.3**
**Given** 自举完成
**When** 在任意新连接上执行 `PRAGMA journal_mode` / `busy_timeout` / `foreign_keys` / `synchronous`
**Then** 分别返回 `wal`（大小写不敏感）/ `5000` / `1` / `1`
**And** 任一断言失败时，进程打印一行可读中文原因并以**非零码**退出（AR-7：不得静默退化）

**AC-1.1.4**
**Given** 端口已被占用，或数据库文件所在目录不可写
**When** 启动
**Then** 进程以非零码退出，并打印**一行**可读中文原因
**And** 不出现静默挂起或无输出的等待

**AC-1.1.5**
**Given** 已有数据在用的 `.sqlite` 文件
**When** 删除该文件并重启
**Then** 系统回到初始种子状态（可重建、无残留表）
**And** 全部业务数据只存在于仓库根目录下**一个** `.sqlite` 文件中（其 `-wal`/`-shm` 同目录，且已被 `.gitignore` 覆盖）

**AC-1.1.6**
**Given** 仓库根目录
**When** 扫描文件树
**Then** 不存在 `package.json`、`vite.config.*`、`node_modules`、`dist`
**And** `requirements.txt` 同时含 `Flask>=3.1.0` 与 `Werkzeug>=3.1.0`（两条均为**下限**，AR-9）

**AC-1.1.7**
**Given** 建表完成
**When** 执行 `PRAGMA index_list('loans')` 与 `PRAGMA index_info('ux_loans_active_item')`
**Then** 存在名为 `ux_loans_active_item` 的索引，`partial = 1`，索引列**仅** `item_id`（D-018：不是 `(user_id, item_id)`）
**And** 直接 `UPDATE items SET status='borrowed'` 被 `CHECK` 约束拒绝并抛 `IntegrityError`（AR-4）

**AC-1.1.8**
**Given** 全项目源码
**When** 检索 `sqlite3.connect(`
**Then** 只命中 `db.py` 中的 `get_db()` 一处（AR-6：唯一连接入口，禁止绕过）

### Story 1.2：学号登录、登出与会话访问控制

作为**学生**，
我希望 用学号 + 密码登录后，系统记住我是谁，并且只有登录后我才能做借还这类写操作，
以便 浏览不被门槛拦住，而「借东西」这个动作有明确的责任人（FR-1、UJ-1）。

**关联**：FR-1、AR-8、AR-10、ADR-003、ADR-004、D-011
**依赖**：Story 1.1（表结构与种子账号）
**规模**：单次开发会话可完成（登录/登出路由 + `before_request` 守卫 + 登录页模板 + 会话配置）

**技术要点**：密码哈希统一走 `security.py` 一个函数；会话用 Flask 签名 cookie（ADR-003）；越权访问 `/admin/*` 返回 403 而非 302（已登录的人不是「没登录」）。

**验收标准：**

**AC-1.2.1**
**Given** 种子学生账号与正确密码
**When** `POST /login`
**Then** 返回 **302**，`Location` 为 `/items`（无 `next` 时）
**And** 响应包含会话 cookie
**And** 用该 cookie `GET /my-loans` 返回 **200**

**AC-1.2.2**
**Given** 登录表单
**When** 提交「学号不存在」「密码错误」「学号为空」「密码为空」四种输入之一
**Then** 四种情况一律返回 **401** + 错误码 `INVALID_CREDENTIALS`
**And** 页面重新渲染登录表单并显示**同一句**提示「学号或密码不正确」
**And** 不建立任何会话（响应不含会话 cookie）

**AC-1.2.3**
**Given** 已登录会话
**When** `GET /login`
**Then** 返回 **302** 到 `/items`
**And** 不重复渲染登录表单

**AC-1.2.4**
**Given** 已登录会话
**When** `POST /logout`
**Then** 返回 **302** 到 `/items`
**And** 响应指示浏览器清除会话 cookie，此后浏览器不再携带该 cookie，`GET /my-loans` 返回 **302** 到 `/login`
**And** 已知限制被如实记录：无状态签名 cookie 无法在服务端吊销，**直接重放登出前保存的 cookie 副本在 24 小时内仍可能返回 200**（ADR-003 §4、D-019）；该行为不写进断言，只写进 `README` 已知限制与回顾

**AC-1.2.5**
**Given** 未登录
**When** 访问 `/my-loans`、`POST /borrow`、`POST /return/<loan_id>`、`/admin/*` 任一
**Then** 返回 **302** 到 `/login?next=<原路径>`
**And** 登录成功后跳回 `<原路径>`

**AC-1.2.6**
**Given** 未登录访客
**When** 访问 `GET /items` 或 `GET /items?q=胶枪`
**Then** 返回 **200** 并正常渲染（FR-2 的开放浏览，D-004）

**AC-1.2.7**
**Given** 已登录的**学生**账号
**When** 访问 `/admin/items`
**Then** 返回 **403** + 错误码 `FORBIDDEN`，页面提示「仅管理员可访问」
**And** **不**重定向到登录页

**AC-1.2.8**
**Given** 一个已登录会话
**When** 闲置 **超过 24 小时**后访问受保护页面
**Then** 返回 **302** 到登录页并提示「登录已过期」
**And** 闲置不足 24 小时时同一请求返回 **200**

**AC-1.2.9**
**Given** 种子账号的密码
**When** 检查 `users.password_hash` 列
**Then** 值以 `pbkdf2:sha256` 前缀存储（显式 `method`，AR-8）
**And** 用已知明文密码登录后，检索响应体与日志，**不出现**明文密码或哈希

**AC-1.2.10**
**Given** 一个不存在的学号
**When** 提交登录
**Then** 仍然调用一次 `check_password_hash`（对固定的假哈希），调用次数恰好 **1**（以 monkeypatch 计数断言）
**And** 该请求与「密码错误」请求返回完全相同的状态码、错误码与文案（ADR-004 防时序侧信道 + D-011 语义合并）

### Story 1.3：物品列表与关键字搜索

作为**访客或学生**，
我希望 不登录就能看到全部可借物品、用关键字筛出我要的那件，并一眼看出它现在在不在、什么时候回来，
以便 我走到班委工位之前就知道有没有白跑（FR-2、UJ-1）。

**关联**：FR-2、AR-4、AR-5、ADR-007 §2.2、D-004、D-013（额度指示部分不在本故事，见 Story 2.5）
**依赖**：Story 1.1（表与种子）、Story 1.2（会话，用于区分访客与登录用户）
**规模**：单次开发会话可完成（`list_items_with_state()` + 列表/搜索路由 + 模板）

**技术要点**：状态一律来自 `list_items_with_state(...)` 这一个派生查询（AR-5），不得另写第二份 SQL，也不得引入库存计数列；`q` 传入 SQL 前按字面量转义 `%` 与 `_`（用 `LIKE ... ESCAPE`）。

**验收标准：**

**AC-1.3.1**
**Given** 库中有 `book` 与 `equipment` 两类共 6 件非停用物品
**When** 匿名 `GET /items`
**Then** 返回 **200**
**And** 先列 `book` 后列 `equipment`，组内按名称升序
**And** 不出现任何 `unavailable` 物品

**AC-1.3.2**
**Given** 列表中有一件名称含「胶枪」的物品
**When** `GET /items?q=胶枪`
**Then** 返回 **200**，结果只含名称包含「胶枪」的非停用物品
**And** 匹配忽略英文大小写与关键字首尾空白（`?q=%20Glue%20` 与 `?q=glue` 结果一致）

**AC-1.3.3**
**Given** 搜索框
**When** 输入单个 `%` 或单个 `_`
**Then** 按普通字符匹配，**不**返回全部物品（通配符被转义）

**AC-1.3.4**
**Given** 请求 `GET /items` 且 `q` 缺失、或 `q` 为纯空白字符串
**When** 渲染
**Then** 等同于无搜索，返回全部非停用物品

**AC-1.3.5**
**Given** 关键字无任何匹配
**When** `GET /items?q=不存在的名字`
**Then** 返回 **200**（不是 404）
**And** 渲染空状态文案「没有找到相关物品」

**AC-1.3.6**
**Given** 一件物品存在未归还借阅记录
**When** 渲染列表
**Then** 该条目标记为「在借」并展示**应还日期**
**And** 匿名请求的响应 HTML 中**不出现**借阅人姓名
**And** 已登录用户请求的响应 HTML 中出现借阅人姓名

**AC-1.3.7**
**Given** 任意列表或搜索响应
**When** 检索响应体
**Then** **不出现**任何学号字符串（种子学号逐一比对，0 命中）

**AC-1.3.8**
**Given** 任意列表或搜索响应
**When** 检查响应头
**Then** 含 `Cache-Control: no-store`

**AC-1.3.9**
**Given** 借阅记录行数与 `items.status` 的初始快照
**When** 连续执行两次相同搜索请求
**Then** 两次响应体一致
**And** `loans` 行数与 `items.status` 与快照逐字段一致（只读操作不产生副作用）

**AC-1.3.10**
**Given** 50 条物品规模的种子数据
**When** 对 `GET /items` 与 `GET /items?q=` 各发 20 次请求
**Then** 服务端处理耗时 **p95 < 200ms**（PRD FR-2 的 Feature-specific NFR，A-3）

---

## 4. Epic 2：借阅、归还与并发一致性

**目标**：借得成、还得掉、抢不到时有话说、且数据库能证明没有超卖。
**覆盖**：FR-3、FR-4、FR-5、NFR-1.1~NFR-1.5。**故事数：5。**
**Epic 完成定义**：5 步脚本（打开首页 → 搜索 → 借阅 → 我的借阅 → 归还）闭合；`pytest` 中两个并发用例各 20 轮通过；D-021 的白盒用例通过；`grep` 证明归还路径不碰 `items`。

> **本史诗的拆分纪律**：NFR-1.1（Story 2.3）与 NFR-1.2（Story 2.4）**必须是两个故事**，因为它们测的是两套完全不同的底层机制——前者考数据库部分唯一索引，后者考 `BEGIN IMMEDIATE` 写事务。合并会导致实施时「只建唯一索引、额度校验做成先查后写」被蒙混过关（PRD NFR-1.2 明文要求，架构索引 §3 第 4 条）。

### Story 2.1：借阅物品（六步判定与应还日期）

作为**学生**，
我希望 点一下「借阅」就把东西借到手，并且失败时得到一个能看懂、能区分的理由，
以便 我知道东西是不是我的、什么时候该还，而不是面对一句笼统的「操作失败」（FR-3、UJ-1）。

**关联**：FR-3、FR-5（限额拦截部分）、NFR-1.5、AR-1、AR-10、ADR-002 §2.2、D-006、D-008、D-016
**依赖**：Story 1.2（登录态）、Story 1.3（列表页与派生状态）
**规模**：单次开发会话可完成（`borrow_item()` 服务函数 + 错误码常量 + 列表页提示区）

**技术要点**：整个写路径包在 `BEGIN IMMEDIATE` 内；②③ 由**一条** `SELECT id, status FROM items WHERE id=?` 同时判定；④⑤ 由**一条**聚合查询同时算出；⑥ 捕获 `IntegrityError` 后与 ④ 输出完全一致的响应。

**验收标准：**

**AC-2.1.1**
**Given** 已登录、当前在借 0 件，目标物品 `available` 且无未归还记录
**When** `POST /borrow`（`item_id`）
**Then** 返回 **302** 到 `/items`，并提示「借阅成功，应还日期 YYYY-MM-DD」
**And** `loans` 新增恰好 1 条：`returned_at IS NULL`、`due_at = borrowed_at + 7 天`（按天为整数，不做时分秒漂移）

**AC-2.1.2**
**Given** 借阅刚成功
**When** 立即 `GET /items`
**Then** 该物品显示为「在借」并展示应还日期（响应头 `no-store`，不依赖缓存）

**AC-2.1.3**
**Given** 物品已被**他人**借走（存在未归还记录）
**When** 该用户 `POST /borrow`
**Then** 返回 **409** + `ALREADY_BORROWED`，提示「该物品已被借出」
**And** 列表刷新为最新状态，`loans` 行数不变

**AC-2.1.4**
**Given** `item_id` 不存在
**When** `POST /borrow`
**Then** 返回 **404** + `RESOURCE_NOT_FOUND`（D-011：与「不可见」同一语义）

**AC-2.1.5**
**Given** 物品 `status='unavailable'`
**When** 已登录用户 `POST /borrow`
**Then** 返回 **409** + `ITEM_UNAVAILABLE`
**And** 不产生借阅记录

**AC-2.1.6**
**Given** 用户已持有该物品（存在未归还记录）
**When** 对该物品再次 `POST /borrow`（模拟双击的第二次）
**Then** 返回 **409** + `ALREADY_BORROWED`
**And** 该响应与「被唯一索引兜底拦下」（④ 与 ⑥ 两条路径）的状态码、错误码、提示文案**逐字一致**
**And** 不新增记录

**AC-2.1.7**
**Given** 用户当前在借 **3** 件
**When** 借一件可借物品
**Then** 返回 **409** + `LIMIT_EXCEEDED`，提示「你已借满 3 件，请先归还」
**And** `loans` 行数与 `items.status` 均不变

**AC-2.1.8**
**Given** 构造出「同一请求同时命中多条判定」的四种组合
**When** 分别发起请求
**Then** 返回值严格按六步顺序取**序号最小**的那一条，四种组合的期望如下表：

| 组合 | 期望 |
|---|---|
| 未登录 + `item_id` 不存在 | 302 → `/login?next=` |
| `item_id` 不存在 + 用户已满额 | 404 `RESOURCE_NOT_FOUND` |
| 物品已停用 + 用户已满额 | 409 `ITEM_UNAVAILABLE` |
| 本人已持有 + 用户已满额 | 409 `ALREADY_BORROWED` |

**And** ①②③④⑤⑥ 的完整顺序在实现中被写成单一路径，测试以上表四行为准

**AC-2.1.9**
**Given** 借阅服务层源码
**When** 评审扫描
**Then** 对 `items` 的读取只出现**一条** `SELECT`（存在性与停用状态读同一行，D-008）
**And** ④ 与 ⑤ 由**同一条**聚合查询一次算出（查询次数断言：单次借阅对 `loans` 的读取为 1 次）

**AC-2.1.10**
**Given** 借阅服务函数
**When** 检查事务边界
**Then** 额度校验的 `COUNT` 与 `INSERT` 位于**同一个** `BEGIN IMMEDIATE` 事务内（AR-1、D-009）
**And** 全项目检索 `BEGIN DEFERRED` 命中 **0** 次

**AC-2.1.11**
**Given** 任一失败请求（404/409）执行前的 `loans` 行数与 `items` 全字段快照
**When** 请求返回失败
**Then** 事后 `loans` 行数与 `items.status` 与快照**逐字段一致**（NFR-1.5，原子性）

**AC-2.1.12**
**Given** 用户有 1 条**逾期**记录 + 2 条正常在借（合计 3 件）
**When** 借第 4 件
**Then** 返回 **409** + `LIMIT_EXCEEDED`（逾期记录计入额度）
**And** **Given** 用户有 1 条逾期记录 + 1 条正常在借（合计 2 件），**When** 借一件新的可借物品，**Then** 返回 **302** 成功（逾期本身不构成拦截）

### Story 2.2：归还物品（条件 UPDATE、停用物品保持停用）

作为**借阅者**，
我希望 在我的借阅里点一次「归还」就把东西还掉、额度立刻回来，即使我已经逾期，
以便 我不用找班委、也不会因为还晚了而被卡住（FR-4、UJ-2）。

**关联**：FR-4、NFR-1.3、AR-3、AR-4、ADR-002 §2.3、ADR-007 §2.3、D-005、D-011、D-014、D-020
**依赖**：Story 2.1（需要能产生在借记录）、Story 1.2（登录态）
**规模**：单次开发会话可完成（`return_loan()` + `/my-loans` 最小可用版 + 确认页）

**技术要点**：只用条件 `UPDATE ... WHERE id=? AND user_id=? AND returned_at IS NULL`，以 `rowcount` 判成败（AR-3）；`rowcount==0` 时再用一次 `SELECT` 区分「已归还 409」与「不存在/非本人 404」。停用操作在本故事**用直接 SQL 注入**（管理入口在 Epic 3 的 Story 3.3 提供），以避免 Epic 2 依赖 Epic 3。

**验收标准：**

**AC-2.2.1**
**Given** 一条属于本人的未归还记录
**When** `POST /return/<loan_id>`
**Then** 返回 **302** 到 `/my-loans` 并提示「已归还」
**And** 该记录 `returned_at` 写入服务端当前时间（非空，且落在请求前后的时间窗内）

**AC-2.2.2**
**Given** 归还成功
**When** `GET /items`
**Then** 该物品不再显示借阅人与应还日期，展示态回到「可借」
**And** 该变化由派生查询算出（`loans` 无未归还记录即成立），不依赖任何 `items` 写入

**AC-2.2.3**（D-005 用例 A，独立断言）
**Given** 物品已借出，且 `items.status` 被置为 `'unavailable'`（本故事以直接 SQL 构造）
**When** 借阅者归还该记录
**Then** `loans.returned_at IS NOT NULL`
**And** `items.status` 仍为 `'unavailable'`（不自动上架）
**And** 该物品不出现在学生列表 `GET /items` 中

**AC-2.2.4**
**Given** 一条逾期记录（`due_at` 已过、`returned_at IS NULL`）
**When** 借阅者归还
**Then** 返回 **302** 并提示「已归还」（逾期不影响归还）
**And** 归还后该记录不再被标记为逾期，页面不再标红

**AC-2.2.5**
**Given** 一条已归还记录
**When** 再次 `POST /return/<loan_id>`
**Then** 返回 **409** + `ALREADY_RETURNED`，提示「该记录已归还」
**And** `returned_at` 原值不被覆盖（前后逐字节一致）

**AC-2.2.6**
**Given** 一条**他人**的在借记录，以及一个**不存在**的 `loan_id`
**When** 分别 `POST /return/<id>`
**Then** 两者均返回 **404** + `RESOURCE_NOT_FOUND`
**And** 两个响应的状态码、错误码、提示文案**完全一致**（D-011）

**AC-2.2.7**
**Given** 未登录
**When** `POST /return/<loan_id>`
**Then** 返回 **302** 到 `/login?next=/return/<loan_id>`（先于归属判断，顺序 ①）

**AC-2.2.8**
**Given** 用户当前在借 3 件
**When** 归还 1 件后**立即**借一件新的可借物品
**Then** 不再返回 `LIMIT_EXCEEDED`，返回 **302** 成功（额度在同一请求内释放）

**AC-2.2.9**（NFR-1.3，并发归还）
**Given** 一条未被归还的记录
**When** 两个线程**同时** `POST /return/<loan_id>`
**Then** 状态码集合**恰好**为 `{302, 409}`，失败方错误码为 `ALREADY_RETURNED`
**And** `returned_at` 只被写入一次，且并发结束后其值不再变化
**And** 重复执行 20 轮，每轮断言同上

**AC-2.2.10**
**Given** 归还路径的全部源码
**When** 检索 `UPDATE items`
**Then** **0 命中**（AR-3、D-014：物品状态的唯一修改入口是管理员）

**AC-2.2.11**
**Given** 归还实现
**When** 检查写法
**Then** 使用条件 `UPDATE ... WHERE id=? AND user_id=? AND returned_at IS NULL`，并以 `rowcount` 判定成败
**And** `rowcount == 0` 时通过一次额外 `SELECT` 区分 409 `ALREADY_RETURNED` 与 404 `RESOURCE_NOT_FOUND`

### Story 2.3：NFR-1.1 同一物品并发借阅 —— 部分唯一索引的物理兜底

作为**产品负责人**，
我希望 有硬证据证明「两个人同一秒抢同一件东西，数据库只允许一个人拿到」，
以便 整个产品承诺的「可查、可数」不是一句口号（NFR-1.1、UJ-4）。

**关联**：NFR-1.1、NFR-1.4、NFR-1.5、AR-1、AR-2、ADR-002 §2.1/§4、D-009、D-018、**D-021**、SM-2
**依赖**：Story 2.1（借阅写路径）、Story 1.1（索引已建）
**规模**：单次开发会话可完成（并发测试脚手架 + 白盒索引测试）
**说明**：本故事**只**覆盖物品唯一性（NFR-1.1）。用户额度并发（NFR-1.2）是 **Story 2.4**，两者测的底层机制不同，不得合并。

**验收标准：**

**AC-2.3.1**
**Given** 一件 `available` 且无未归还记录的物品，两名均已登录且均未满额的用户
**When** 两个线程通过 **barrier 对齐后同时**发起 `POST /borrow`（各自独立 HTTP 连接 / 独立数据库连接）
**Then** HTTP 状态码集合**恰好**为 `{302, 409}` —— 一个成功、一个失败，无一例外
**And** 失败方错误码**恰好**为 `ALREADY_BORROWED`

**AC-2.3.2**
**Given** 上述并发请求结束
**When** 查询 `SELECT COUNT(*) FROM loans WHERE item_id = ? AND returned_at IS NULL`
**Then** 结果**恰好 1**（不是 0，不是 2）

**AC-2.3.3**
**Given** 同一实验设置
**When** 连续重复 **20 轮**
**Then** 每轮都重新断言 AC-2.3.1 与 AC-2.3.2
**And** 20 轮中**没有任何一轮**出现 2 条未归还记录

**AC-2.3.4**（D-021 强制验收项，本阶段最高优先级的一条）
**Given** 一条已存在的在借记录（`item_id = X`，`returned_at IS NULL`），且测试持有数据库连接、**不经过**任何服务层或路由代码
**When** 直接对该 `item_id` 再插入一条未归还的借阅记录
**Then** 数据库抛出 `IntegrityError`（`UNIQUE constraint failed: loans.item_id`），第二次插入被物理拒绝
**And** 插入失败后该 `item_id` 的未归还记录仍**恰好 1 条**
**And** 本用例即为 D-021 要求的原文验收：**「用 SQL 直接绕过服务层插入重复在借记录，断言数据库抛出 IntegrityError，证明唯一索引确实存在。」**
**And** 该用例与 AC-2.3.1~2.3.3 **并列存在、不可相互替代**——前者证明索引存在，后者证明并发行为

**AC-2.3.5**
**Given** 索引定义
**When** 执行 `PRAGMA index_list('loans')` 与 `PRAGMA index_info('ux_loans_active_item')`
**Then** `ux_loans_active_item` 的 `partial = 1`，索引列**仅** `item_id`
**And** 该索引带 `WHERE returned_at IS NULL` 条件

**AC-2.3.6**
**Given** 该物品唯一的未归还记录已被归还
**When** 另一名用户借**同一件**物品
**Then** 返回 **302** 成功（部分索引不永久占用历史组合键，FR-3「归还后可再借」成立）

**AC-2.3.7**（NFR-1.4 无中间态）
**Given** 并发场景结束
**When** 渲染 `GET /items` 并同时查 `loans` 的未归还计数
**Then** 二者一致：列表显示「在借」⇔ `COUNT = 1`；显示「可借」⇔ `COUNT = 0`
**And** 不存在「有在借记录但显示可借」或「无在借记录但显示在借」

**AC-2.3.8**（NFR-1.5 失败无副作用）
**Given** 20 轮并发前的 `items` 全字段快照与 `loans` 总行数
**When** 20 轮结束
**Then** `loans` 总行数 = 成功请求数（每轮 1 条）
**And** `items.status` 与快照逐字段一致（借阅不改物品状态）

**AC-2.3.9**
**Given** 并发测试代码
**When** 评审阅读
**Then** 两个请求由 `threading.Barrier` + 两个线程（或 `ThreadPoolExecutor`）真正并发发起，**不是**两次串行请求
**And** 测试在**单进程 `threaded=True`** 的真实部署形态下运行（ADR-005 §6）
**And** 以 `pytest` 可重复执行，命令与结果写入 `retrieval` 证据（SM-2）

**AC-2.3.10**
**Given** 借阅服务层的异常处理
**When** 注入一个**非唯一约束**的 `IntegrityError`（如外键失败）
**Then** 该异常**不**被映射成 409 `ALREADY_BORROWED`，而以 500 或明确的内部错误呈现
**And** 只有唯一约束冲突（`UNIQUE constraint failed: loans.item_id`）才映射为 409（ADR-002 §4）

### Story 2.4：NFR-1.2 同一用户并发超额 —— `BEGIN IMMEDIATE` 的事务原子性

作为**产品负责人**，
我希望 有硬证据证明「一个还差 1 件满额的用户，同时借两件东西不会借到 4 件」，
以便 限额不是「通常有效」的提示，而是写事务保证的不变量（NFR-1.2）。

**关联**：NFR-1.2、NFR-1.5、AR-1、AR-5、AR-2、ADR-002 §3.5、D-009、D-012、D-013、**D-021**
**依赖**：Story 2.1（借阅写路径与限额校验）、Story 1.1（表结构）
**规模**：单次开发会话可完成（另一份并发测试 + 额度函数唯一性断言）
**说明**：本故事**只**覆盖用户额度不变量（NFR-1.2），与 Story 2.3 的物品唯一性**相互独立**；两者各自有独立的并发验收标准与独立的失败表现（超卖 vs 越限）。

**验收标准：**

**AC-2.4.1**
**Given** 用户 U 当前在借 **2** 件（额度 3，只差 1 件），两件**不同**的可借物品 `A`、`B`
**When** 两个线程通过 barrier 对齐后**同时** `POST /borrow`（一个借 A、一个借 B）
**Then** 恰好 **1 个返回 302**、**1 个返回 409 + `LIMIT_EXCEEDED`**

**AC-2.4.2**
**Given** 上述并发结束
**When** 查询 `SELECT COUNT(*) FROM loans WHERE user_id = ? AND returned_at IS NULL`
**Then** 结果**恰好 3**（不得为 4）

**AC-2.4.3**
**Given** 同一实验设置
**When** 连续重复 **20 轮**
**Then** 每轮重新断言 AC-2.4.1 与 AC-2.4.2
**And** 20 轮中**没有任何一轮**出现在借数为 4

**AC-2.4.4**（D-021 强制验收项，与 Story 2.3 的 AC-2.3.4 并列、各自独立执行）
**Given** 一条已存在的在借记录（`item_id = X`，`returned_at IS NULL`），且测试持有数据库连接、**不经过**任何服务层或路由代码
**When** 直接对该 `item_id` 再插入一条未归还的借阅记录
**Then** 数据库抛出 `IntegrityError`（`UNIQUE constraint failed: loans.item_id`），第二次插入被物理拒绝
**And** 本用例即为 D-021 要求的原文验收：**「用 SQL 直接绕过服务层插入重复在借记录，断言数据库抛出 IntegrityError，证明唯一索引确实存在。」**
**And** 该断言可复用 Story 2.3 的同一份测试代码，但必须在本故事的测试集中独立执行、独立计数（合并执行即视为 NFR-1.1 与 NFR-1.2 被合并）

**AC-2.4.5**（为什么额度必须另有机制：白盒反证）
**Given** 用户 U 在借 1 件（`item_id = A`）
**When** 绕过服务层，用 SQL 直接插入**同一用户、不同物品 B** 的第 2 条未归还记录
**Then** 数据库**接受**该插入（不抛异常）
**And** 由此证明：**额度没有任何数据库级兜底**，`COUNT ≤ 3` 只能由 `BEGIN IMMEDIATE` 的事务原子性保证 —— 这正是 NFR-1.2 必须独立成故事、且必须真并发测试的理由

**AC-2.4.6**
**Given** 借阅服务函数
**When** 检查事务与查询结构
**Then** 额度校验与 `INSERT` 在同一个 `BEGIN IMMEDIATE` 内（先后顺序：先校验、后插入）
**And** 全项目检索 `BEGIN DEFERRED` 命中 **0** 次，`isolation_level` 未被留在 Python 默认的隐式事务模式（ADR-005 §2.2）

**AC-2.4.7**
**Given** 全项目源码
**When** 检索额度计数 SQL（`COUNT(*)` 且 `FROM loans` 且 `returned_at IS NULL` 的聚合）
**Then** **只有一处**，位于 `get_remaining_quota(student_id)` 内，且函数体内只含这一条聚合查询（AR-5、D-013）
**And** 借阅前置校验与页面限额指示均调用该函数，无第二份实现

**AC-2.4.8**
**Given** 用户 U 在借 2 件、用户 V 在借 0 件，两件不同的可借物品
**When** 两人并发各自借一件
**Then** **两个请求都返回 302**（写事务串行化不得导致误拒）

**AC-2.4.9**
**Given** 任一因 `LIMIT_EXCEEDED` 失败的请求
**When** 比对请求前后的 `loans` 行数与 `items.status`
**Then** **逐字段一致**（失败无副作用，NFR-1.5）

**AC-2.4.10**
**Given** 管理员账号当前在借 3 件
**When** 管理员借第 4 件
**Then** 返回 **409** + `LIMIT_EXCEEDED`
**And** 借阅源码中不存在任何以角色为条件的限额分支（检索 `role` 出现在限额逻辑中命中 0 次，D-012）

### Story 2.5：我的借阅与限额指示（额度只有一处真相）

作为**学生**，
我希望 在一个页面上看到我当前借着什么、哪天该还、有没有逾期，以及我还能借几件，
以便 我不用翻聊天记录，也不用自己数（FR-3 的 `/my-loans`、FR-5 的指示）。

**关联**：FR-3（`/my-loans` 段）、FR-5、AR-5、ADR-007 §2.2、D-007、D-013
**依赖**：Story 2.1、Story 2.2（需要借还闭环产生数据）
**规模**：单次开发会话可完成（`/my-loans` 路由与模板 + 列表页限额指示区）

**技术要点**：限额指示的 X 由 `get_remaining_quota()` 换算（X = 3 − 剩余），换算只在模板层做一次；`/items` 与 `/my-loans` 复用同一函数与同一文案格式（D-013）。

**验收标准：**

**AC-2.5.1**
**Given** 用户有 2 条未归还记录与 3 条已归还记录
**When** `GET /my-loans`
**Then** 返回 **200**，只列出那 **2** 条未归还记录
**And** 已归还记录不出现（`returned_at IS NOT NULL` 一律过滤）

**AC-2.5.2**
**Given** 一条未归还记录
**When** 渲染 `/my-loans`
**Then** 该行展示物品名称、借出时间、应还日期
**And** 若当前时间晚于应还日期，该行标红并显示「已逾期 N 天」，N = 当前日期 − 应还日期的天数差（`due_at` 当天不标红）

**AC-2.5.3**
**Given** 当前在借 X 件
**When** 渲染 `/my-loans` 与登录后的 `/items`
**Then** 两个页面顶部都显示「已借 X / 3」
**And** 两处使用**同一**服务层函数与**同一**文案格式（D-013）

**AC-2.5.4**
**Given** 在借 2 件
**When** 归还 1 件后立即重新渲染 `/my-loans`
**Then** 指示变为「已借 1 / 3」（同一请求内释放，无需重新登录或等待）

**AC-2.5.5**
**Given** 匿名访客
**When** 渲染 `/items`
**Then** **不显示**限额指示

**AC-2.5.6**
**Given** 用户没有任何未归还记录
**When** `GET /my-loans`
**Then** 返回 **200** 并渲染空状态文案「当前没有在借物品」

**AC-2.5.7**
**Given** 另一个用户存在未归还记录
**When** 本用户 `GET /my-loans`
**Then** 响应中不出现他人的记录（查询按 `user_id` 过滤，越权不可见）

**AC-2.5.8**
**Given** 一次列表页渲染
**When** 统计额度查询次数（以 monkeypatch/计数断言）
**Then** 额度查询次数**恒为 1**，与列表长度无关（不在渲染中循环查询）

**AC-2.5.9**
**Given** 全项目源码
**When** 检索字面量 `3` 出现在限额校验与文案中的位置
**Then** 限额值只在**一处**常量定义（如 `BORROW_LIMIT = 3`），校验与文案均引用该常量
**And** 不存在「提示写 3、校验按 5」的漂移

---

## 5. Epic 3：管理员维护物品清单

**目标**：清单能新增、能下架、能上架、能删除，且每个动作的拒绝条件都确定。
**覆盖**：FR-6。**故事数：4。**
**Epic 完成定义**：四类边界（在借物品、停用物品、有已归还记录的物品、从未被借过的物品）各执行一次操作都得到确定结果；`grep` 证明 `UPDATE items` 只出现在停用与恢复两处。

### Story 3.1：管理员新增物品与管理列表

作为**管理员**，
我希望 录入一件新物品（名称 + 类别），并在一个页面里看到包括已停用项在内的全部清单，
以便 班里的东西进了抽屉就能立刻被搜到（FR-6 新增、UJ-3 前置）。

**关联**：FR-6（新增、权限入口、管理列表）、AR-4、AR-10、D-011
**依赖**：Story 1.2（管理员登录与 403）、Story 1.3（学生端列表，用于验证「立即可搜到」）
**规模**：单次开发会话可完成（`/admin/items` 列表与新增表单 + `create_item()`）

**验收标准：**

**AC-3.1.1**
**Given** 未登录
**When** 访问 `/admin/items` 或 `POST /admin/items`
**Then** 返回 **302** 到 `/login?next=<原路径>`

**AC-3.1.2**
**Given** 已登录的**学生**
**When** 访问 `/admin/items` 或任一 `/admin/*` 写操作
**Then** 返回 **403** + `FORBIDDEN`
**And** 不产生任何数据变更（`items` 行数与内容不变）

**AC-3.1.3**
**Given** 管理员提交名称「热熔胶枪 #3」、类别 `equipment`
**When** `POST /admin/items`
**Then** 返回 **302** 到管理列表并提示「已添加」
**And** `items` 新增 1 条，`status` 默认 `available`
**And** 该物品立刻可被 `GET /items?q=胶枪` 搜到

**AC-3.1.4**
**Given** 名称字段
**When** 提交空字符串、纯空格字符串、或去首尾空白后长度为 51 的字符串
**Then** 一律返回 **400** + `INVALID_INPUT`
**And** `items` 行数不变
**And** **Given** 去首尾空白后长度为 50 的名称，**When** 提交该名称，**Then** 新增成功（边界值 50 被接受）

**AC-3.1.5**
**Given** 类别字段
**When** 提交 `book` / `equipment` 之外的值（含空值）
**Then** 返回 **400** + `INVALID_INPUT`，不写入

**AC-3.1.6**
**Given** 已存在名为「热熔胶枪」的物品
**When** 再添加一条同名物品
**Then** 新增成功（名称允许重复，不做唯一校验）
**And** 两条记录各自拥有独立 `id`，可独立借还（ADR-006 一物一行）

**AC-3.1.7**
**Given** 管理列表 `GET /admin/items`
**When** 渲染
**Then** 列出**全部**物品，**包含** `unavailable` 项
**And** 停用项被明确标注为「已停用」
**And** 有未归还记录的物品标注当前在借人姓名

**AC-3.1.8**
**Given** 新增与列表的全部写路径
**When** 检索源码
**Then** 不存在向 `items.status` 写入 `'borrowed'` 的语句（AR-4）
**And** 表单为服务端渲染的 HTML `form` + `POST`（无 JSON API、无 `fetch`/XHR，ADR-001）

### Story 3.2：删除物品（在借拦截 + 同事务级联清理）

作为**管理员**，
我希望 删除一件不再提供的物品，但在它还被别人拿着时系统能拦住我，
以便 我不会因为手滑而让一条在借记录凭空消失（FR-6 删除、UJ-3）。

**关联**：FR-6（删除）、AR-4、AR-10、ADR-002 §2.1、D-010、D-020
**依赖**：Story 3.1（管理列表与权限）、Story 1.1（`loans` 表结构）
**规模**：单次开发会话可完成（`delete_item()` + 确认页 + 级联清理）

**技术要点**：`item_id` 外键**不带** `ON DELETE CASCADE`（D-020）；删除在 `BEGIN IMMEDIATE` 内先 `DELETE FROM loans WHERE item_id=? AND returned_at IS NOT NULL`，再 `DELETE FROM items WHERE id=?`。

**验收标准：**

**AC-3.2.1**
**Given** 物品存在**未归还**借阅记录（本故事以 SQL 直接构造，不依赖 Epic 2）
**When** 管理员 `POST /admin/items/<id>/delete`
**Then** 返回 **409** + `ITEM_IN_BORROW`，提示「该物品在借中，无法删除」
**And** `items` 行数与 `loans` 行数均不变（逐字段比对）

**AC-3.2.2**
**Given** 物品无未归还记录，但名下有 3 条**已归还**记录
**When** 管理员 `POST /admin/items/<id>/delete`
**Then** 返回 **302** 到管理列表并提示「已删除」
**And** 该物品行被删除
**And** 该物品名下 `loans` 记录数为 **0**（已归还记录被同事务级联清理，D-010）

**AC-3.2.3**
**Given** 删除流程
**When** 在 `DELETE FROM loans` 之后、`DELETE FROM items` 之前注入一个异常
**Then** 事务整体回滚：物品仍存在，其已归还记录条数不变
**And** 不出现「物品删了、历史记录还在」或反之的中间态

**AC-3.2.4**
**Given** 一个不存在的 `item_id`
**When** `POST /admin/items/<id>/delete`
**Then** 返回 **404** + `RESOURCE_NOT_FOUND`

**AC-3.2.5**
**Given** 数据表定义
**When** 执行 `PRAGMA foreign_key_list('loans')`
**Then** `item_id` 外键的 `on_delete` **不是** `CASCADE`（D-020：级联删除会静默绕过本故事的业务拦截）

**AC-3.2.6**
**Given** 管理员在管理列表点击「删除」
**When** 尚未提交
**Then** 先渲染确认页（**200**，含物品名称与「确认删除」按钮），删除**只**由 `POST /admin/items/<id>/delete` 执行
**And** 直接在浏览器地址栏 `GET` 该删除路径**不**产生删除（写操作只接受 POST）

**AC-3.2.7**
**Given** 学生账号或未登录访客
**When** 调用删除接口
**Then** 分别返回 **403** `FORBIDDEN` 与 **302** 登录页，且 `items`/`loans` 无变化

### Story 3.3：停用物品（在借也能停用，归还后仍停用）

作为**管理员**，
我希望 在物品坏掉时立刻把它从学生视野里撤下，即使它正在别人手上，
以便 我不会陷入「既不能删也不能下架」的死角，而借阅者照常能还（FR-6 停用、UJ-3）。

**关联**：FR-6（停用）、AR-4、AR-5、ADR-007 §2.1/§2.3、D-003、D-005、D-014
**依赖**：Story 3.1（管理列表）、Story 1.3（学生端列表用于验证消失）
**规模**：单次开发会话可完成（`set_unavailable()` + 管理列表动作按钮）

**验收标准：**

**AC-3.3.1**
**Given** 物品 `status='available'` 且**正被借出**
**When** 管理员 `POST /admin/items/<id>/unavailable`
**Then** 返回 **302** 并提示「已停用」
**And** `items.status` 变为 `'unavailable'`
**And** 该物品上的未归还记录**仍然存在**（不受影响）

**AC-3.3.2**
**Given** 物品已停用
**When** 匿名 `GET /items` 与 `GET /items?q=<该物品名>`
**Then** 该物品**均不出现**（学生端不可见）
**And** 管理员 `GET /admin/items` 仍能看到它，并标注「已停用」

**AC-3.3.3**
**Given** 物品已停用但仍在借（本故事以 SQL 构造该在借记录）
**When** 借阅者 `GET /my-loans`
**Then** 该记录**仍然可见**（停用不影响借阅者的记录）
**And** 借阅者对该记录 `POST /return/<loan_id>` 仍返回 **302** 成功

**AC-3.3.4**
**Given** 物品已停用
**When** 管理员再次 `POST /admin/items/<id>/unavailable`
**Then** 幂等成功：返回 **302** 并提示「已停用」
**And** 不报错，`items.status` 保持 `'unavailable'`

**AC-3.3.5**
**Given** 停用实现
**When** 直接执行 `UPDATE items SET status='borrowed' WHERE id=?`
**Then** 数据库抛 `IntegrityError`（`CHECK` 约束只允许两值，AR-4）
**And** 停用路径的 SQL 只写入 `'unavailable'` 字面量，不出现 `'borrowed'`

**AC-3.3.6**
**Given** 学生账号
**When** `POST /admin/items/<id>/unavailable`
**Then** 返回 **403** + `FORBIDDEN`，`items.status` 不变
**And** **Given** 未登录，**When** 调用同一接口，**Then** 返回 **302** 到登录页，`items.status` 不变

**AC-3.3.7**
**Given** 停用物品上有一条未归还记录
**When** 计算该用户的剩余额度
**Then** 该记录**照常计入**在借数（停用不释放额度，FR-5）

### Story 3.4：恢复上架与状态机边界回归

作为**管理员**，
我希望 修好的东西能一键回到学生视野，并且系统能证明「物品状态只有我一个人能改」，
以便 借阅、归还、停用三条路径都不会偷偷改动物品状态（FR-6 恢复、ADR-007）。

**关联**：FR-6（恢复上架）、AR-4、AR-5、ADR-007 §2.2/§2.3、D-005、D-014、D-015、NFR-1.4
**依赖**：Story 3.3（需要可停用的物品）、Story 1.3（学生端列表）
**规模**：单次开发会话可完成（`set_available()` + 派生函数收敛 + 四态组合回归测试）

**验收标准：**

**AC-3.4.1**
**Given** 物品 `status='unavailable'`
**When** 管理员 `POST /admin/items/<id>/available`
**Then** 返回 **302** 并提示「已恢复上架」
**And** `items.status` 变为 `'available'`
**And** 该物品重新出现在 `GET /items` 与搜索结果中

**AC-3.4.2**
**Given** 物品已是 `available`
**When** 再次 `POST /admin/items/<id>/available`
**Then** 幂等成功：返回 **302**，不报错，`status` 不变

**AC-3.4.3**（D-005 用例 B，独立断言，与用例 A 分开）
**Given** 物品已停用，且其名下仍有未归还记录
**When** 管理员执行恢复上架
**Then** `items.status = 'available'`
**And** 该物品出现在学生列表 `GET /items` 中
**And** 页面按派生态显示为「在借」（`status` 为 `available` 不等于「可借」，ADR-007）
**And** 本用例与 Story 2.2 的 AC-2.2.3（用例 A）**分属两个故事的独立用例**，不合并为一条「归还并恢复」的顺拐用例

**AC-3.4.4**
**Given** 四种状态组合（`available` / 有在借 / `unavailable` / `unavailable` 且有在借）
**When** 渲染学生列表与 `GET /my-loans`
**Then** 展示优先级恒为 `unavailable` > `borrowed` > `available`
**And** 四种组合各有独立断言，`unavailable` 且有在借时学生端**不展示**该物品（但借阅者仍能在 `/my-loans` 看到并归还）

**AC-3.4.5**
**Given** 全项目源码
**When** 检索 `UPDATE items`
**Then** 只命中**两处**：停用与恢复上架（D-014；借阅、归还、删除路径均不得更新 `items.status`）

**AC-3.4.6**
**Given** 全项目源码
**When** 检索「物品 + 在借状态」的派生查询实现
**Then** `list_items_with_state(...)` 是**唯一**实现，学生列表、搜索结果、管理列表均复用它
**And** `EXISTS (SELECT 1 FROM loans ... returned_at IS NULL)` 这类判定只出现在该函数内（AR-5）

**AC-3.4.7**
**Given** 任一并发借阅场景（复用 Story 2.3 的 20 轮实验）
**When** 场景结束后交叉比对
**Then** 列表渲染出的状态与 `loans` 未归还计数一致（`borrowed` ⇔ `COUNT = 1`），无中间态（NFR-1.4）

**AC-3.4.8**
**Given** 学生账号或未登录访客
**When** 调用恢复上架接口
**Then** 分别返回 **403** `FORBIDDEN` 与 **302** 登录页，且 `items.status` 不变

---

## 6. Reviewer Gate 自检（阶段 3）

> 判定方式优先写「脚本/命令」，不写「已检查」。本节每条都可被复跑：核验脚本与原始输出见 [`docs/evidence/gate-stage3.md`](../../docs/evidence/gate-stage3.md)。

| 编号 | 检查项 | 判定方式 | 结果 |
|---|---|---|---|
| A-1 | 史诗数 = 3 | 正则 `^## \d+\. Epic \d+` 计数 | ✅ 3（Epic 1/2/3） |
| A-2 | 故事数 = 12（不多不少） | 正则 `^### Story \d+\.\d+` 计数 | ✅ 12（3 + 5 + 4） |
| A-3 | 每条 AC 为 Given/When/Then 且可测 | 正则 `^\*\*AC-\d+\.\d+\.\d+\*\*` 计数；逐块校验 `Given`/`When`/`Then` 配对（每块 ≥1 且 G == T，W ≥1） | ✅ 110 条，全部配对通过 |
| A-4 | NFR-1.1 与 NFR-1.2 为两个独立故事 | Story 2.3 与 2.4 各自含独立并发 AC（2.3.1~2.3.3 vs 2.4.1~2.4.3） | ✅ 独立，未合并 |
| A-5 | D-021 白盒 AC 出现在并发故事中 | 以 D-021 原文整句做精确匹配，统计故事正文命中次数 | ✅ 2 处（AC-2.3.4、AC-2.4.4），均为逐字原文 |
| A-6 | 无范围蔓延 | 在故事正文区间（`## 3.` ~ `## 6.`）检索 PRD 非目标关键词 | ✅ 0 命中（见 A-6 明细） |
| A-7 | FR 全覆盖 | FR-1~FR-6 逐个映射到故事（§1.5） | ✅ 6/6 |
| A-8 | 无前向依赖 | 逐故事核对「依赖」字段只指向更早故事 | ✅ 12/12 |
| A-9 | 无占位符 | 检索占位符关键字族（4 个全大写标记 + 1 个中文词，清单见核验脚本的 `PLACEHOLDERS` 常量） | ✅ 0 命中 |
| A-10 | 未改写锁定值 | 限额 3、借期 7 天、六步判定顺序、错误码语义 | ✅ 仅引用，未修改 |
| A-11 | 每条 AC 归属唯一故事 | 逐条读，无同一断言重复出现在两个故事 | ✅ 唯一（例外见下方观察项 O-2） |
| A-12 | 故事规模适合单次开发会话 | 逐故事列「规模」字段，均无「同时建全部表」「一次做完一个史诗」 | ✅ 12/12 |

**A-3 明细**：12 个故事共 **110 条 AC**，全部为 Given/When/Then 三段式；断言对象均为可机检项（HTTP 状态码 / 错误码字面量 / SQL 计数 / `PRAGMA` 返回值 / `grep` 命中数 / 时间窗），不存在「用户可以顺利…」这类不可判定的写法。

**A-6 明细（范围守门）**：脚本在故事正文区间（`## 3.` 至 `## 6.`）检索 15 个 PRD 非目标关键词（清单见核验脚本的 `FORBIDDEN` 常量）—— **全部 0 命中**。相关词仅出现在 §0 范围守门与本节（均为非故事内容）。

**待人类裁决的观察项（不阻塞本阶段）**

| 编号 | 观察 | 建议 |
|---|---|---|
| O-1 | 「8 个错误码」的计数与实际枚举不符：PRD §4 逐条可数出 **9** 个（`INVALID_CREDENTIALS`、`FORBIDDEN`、`RESOURCE_NOT_FOUND`、`ALREADY_BORROWED`、`ITEM_UNAVAILABLE`、`LIMIT_EXCEEDED`、`ALREADY_RETURNED`、`ITEM_IN_BORROW`、`INVALID_INPUT`）。ADR-001 与架构索引沿用了「8 个」这一表述 | 本阶段**不改写** PRD（AGENTS.md §4：锁定值不得擅改）。故事按 9 个错误码逐个断言；建议在阶段 4 一并订正 PRD §4 与 ADR-001 的措辞，或明确「8」指 4xx 业务错误码且不含 400 的 `INVALID_INPUT` |
| O-2 | 用例 A（D-005：停用 → 归还 → 仍停用）在 Story 2.2（AC-2.2.3）与 Story 3.3（AC-3.3.3）各出现一次；用例 B 只出现在 Story 3.4（AC-3.4.3） | 这是**刻意**的：Story 2.2 用 SQL 直接构造停用态以保持 Epic 2 不依赖 Epic 3；Story 3.3 提供经管理接口的端到端复验。两者共享结论、各自可独立执行，不属于「同一断言重复」 |
| O-3 | FR-5 的「登录后 `/items` 显示限额指示」由 Story 2.5 承载，而非 Story 1.3 | 避免 Story 1.3 前向依赖 Epic 2 的额度函数；Story 1.3 的模板先不渲染该区块，Story 2.5 补齐 |

---

## 7. 交接给阶段 4

- **建议实施顺序**：1.1 → 1.2 → 1.3 → 2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 3.1 → 3.2 → 3.3 → 3.4（与依赖方向一致）。
- **必须先跑通的三个测试**（一票否决项，PRD §8.4）：NFR-1.1 20 轮、NFR-1.2 20 轮、D-021 白盒 `IntegrityError`。三者缺一即判定项目核心失败。
- **`project-context.md`**：实现规约见 [`_bmad-output/project-context.md`](../project-context.md)（15 条，含 snake_case、`BEGIN IMMEDIATE`、归还只写 `loans`、额度单一真相等），阶段 4 每写一个故事前先按它自检。
- **实验 A 对照组**：Story 3.1（管理员添加物品）是对照实验的对照组题目，实施时须保留「裸写」版本作为对照证据（不进入本仓库主线）。

*文档结束。阶段 3 锁定：3 个史诗 / 12 个故事 / 110 条 Given-When-Then 验收标准。*
