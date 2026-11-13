# 对话摘录 · 决策点 2 · AI 指出手册唯一索引挡不住超卖，人类授权修正（ADR-002 / D-018、D-021）

> 来源：DSH NEXT 本地会话转录（`C:\Users\honor\.dsh\sessions\--D-documents-homework--\` 下 `session.v4.jsonl.zstd`），
> 由脚本原文导出：未改写任何对话文字，超长消息在截断处标注「（后略，共 N 字）」。
> 会话 ID：`session-01e7b3c2-3657-447d-826f-9dd38b8387d7` · 会话创建：2026-11-08 15:07:28 · 模型：`deepseek (see raw jsonl)` · 工作区：`D:\documents\homework`

---

### [2026-11-08 15:08:55] **AI（assistant）**

已按阶段 2 的剧本起草 **ADR-001**，停在这里等你评审。

**产出文件**：[ADR-001-rendering.md](_bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/ADR-001-rendering.md)（`status: draft`，未提交，尚未写入 decision-log）

**我这条的建议（拟）：React 18 + Vite SPA + Flask 纯 JSON API**

四段齐全：

| 段 | 要点 |
|---|---|
| 背景 | 5 个页面入口、≤50 条物品、唯一写热点是 `POST /borrow`；承认 PRD §6 锁了技术栈，但把约束理解为「功能边界」而非工程选择 |
| 决定 | React 18 + Vite／`/api/*` JSON／Bearer token／前端构建产物 + 后端双进程 |
| 否决的备选 | Flask + Jinja2 SSR，理由：表现力受限、UI 与业务耦合、多端难复用 |
| 后果 | 正面 3 条；**负面 5 条自己列出**：冲击 NFR-2「一条命令启动」、进程/端口翻倍、会话被迫变 token、错误码与中文文案双份维护、工期 +1–2 天、与上游两份文档正面冲突 |

我在后果里主动写全了成本——这条的成本清单本身就是否决它的证据，评审时可以直接引用。

**两个待你裁定的问题**（文件 §5）：
- Q1：是否愿为「现代感」承担这 5 项代价，尤其 NFR-2 和工期？
- Q2：若采纳，NFR-2 是否从「一条命令」放宽为「两条命令 + 先装 Node」？

---

另外两件事，先报备不展开，等你按节奏处理：

1. **ADR-002 有一处我必须先跟你确认**：playbook 驳点 2-2 写的是借阅表上建 `UNIQUE(user_id, item_id)`。严格说这个索引**挡不住超卖**——它只保证「同一个人不能持有同一物品两次」，而 NFR-1.1 要的是「同一物品同时只能有 1 条在借记录」，两个**不同**用户仍然能同时借走同一件。到 ADR-002 时我会建议改成 `item_id` 上的**部分唯一索引**（`WHERE returned_at IS NULL`）。属于实现层修正，不动 PRD 产品值，但会改你已写进 playbook 的措辞，所以先打招呼。
2. **ADR-003 有一处 PRD 可能不可行**：FR-1 要求登出后「用旧 cookie 访问 `/my-loans` → 302」。Flask 默认的签名 cookie session 是**无状态**的，登出只能清掉浏览器那份副本，服务端无法吊销已签发的 cookie。走浏览器测试能过，但严格意义上不成立。到 ADR-003 我会给出取舍方案。

请裁定 ADR-001：**采纳 React**，还是**按 playbook 驳点 2-1 否决改 SSR**？

---

### [2026-11-08 15:11:37] **人类（user）**

⚔️ 裁决 ADR-001：坚决否决 React，改 SSR
「我否决 React 方案。
理由三条：
① 作业约束和技术栈限制明确禁止前后端分离；
② NFR-2 要求『一条命令启动』，我不懂运维，多一条前端构建链就多一个故障点；
③ 它引入了 Bearer token，这直接推翻了我们阶段 1 定好的 ADR-003（Flask session）。
改用 Flask + Jinja2 服务端直接渲染。
记 ADR-001：决定 = 服务端渲染；否决的备选 = React SPA + REST API；理由 = 运维复杂度与工期。
（注：Q1不采纳，Q2也不放宽。NFR-2 必须是单命令启动，不接受装 Node。）」

🔧 裁决前置报备 1：关于 ADR-002 唯一索引的修正
「完全同意你的修正，是我手册里写错了。
UNIQUE(user_id, item_id) 确实防不住两个不同用户借同一件。你提出的『在 item_id 上建 WHERE returned_at IS NULL 的部分唯一索引』在逻辑上完美闭环。
授权你在写 ADR-002 时，直接采用你的方案。同时，在生成 ADR-002 后，顺手把 review-playbook.md 里的那句错话改过来，并加上备注『原手册错误，经架构阶段验证修正』，这本身就是一个极好的决策留痕。」

🔧 裁决前置报备 2：关于 ADR-003 Session 登出问题
「同意你的严谨。 这是纯架构层面的底层限制。
给出取舍方案：采用 Flask-Session（服务端 Session 存储） 或者直接在 Redis/内存里维护黑名单。如果不引入外部依赖，就明确接受这个『浏览器测试能过，但服务端无状态』的现实，并在 ADR-003 里写清：『无状态 session 降低了运维成本，代价是服务端无法主动吊销令牌，v1 接受此风险』。按这个去写 ADR-003。」

🚀 下一步指令
「现在，立即写出 ADR-001（SSR 方案），并按你的计划把 ADR-002（部分唯一索引方案）和 ADR-003（Session 取舍方案）一并产出。
产完之后，别忘了还有 ADR-004（密码存储） 和 ADR-005（WAL 模式与单进程部署），把这 5 条一并提交到 draft 里。
记住我们的铁律：每条 ADR 必须有『决定 / 否决的备选 / 理由』。写完检查一遍，然后 git commit。」

---

### [2026-11-08 18:21:36] **人类（user）**

技术细节核查结果
Werkzeug 默认算法：AI是对的。从 Werkzeug 3.0.0（2023-09-30发布） 开始，generate_password_hash 的默认算法已从 PBKDF2 改为 scrypt。因此，ADR-004 中强制显式传入 method="pbkdf2:sha256" 是保证行为一致性的必要措施，而不是过度设计。

Flask 与 Python 3.14 兼容性：存在已知问题，但可解决。Python 3.14 移除了 pkgutil.get_loader，导致旧版 Flask 崩溃。解决方案是升级到 Flask >= 3.1.0（该版本已移除相关调用），并配套使用 Werkzeug >= 3.1.0。AI 建议的“装不上就退回 3.12”是合理的后备方案。

SQLite WAL 落盘确认：做法正确。执行 PRAGMA journal_mode; 命令，返回值为 wal 即表示 WAL 模式已成功启用。这是一个可靠的一键验证方法。

⚖️ 对 AI 三处“加严”的裁决
裁决 1：外键不用 ON DELETE CASCADE —— 批准，理由充分

你的理由成立：级联删除会静默绕过 FR-6 的业务拦截，属于“用数据库便利性牺牲业务正确性”。事务内显式删除、外键兜底报错，是更符合 NFR-2 可观测性要求的做法。采纳，记录进 ADR-002。

裁决 2：归还用条件 UPDATE —— 批准，这是 NFR-1.3 的直接实现

UPDATE ... WHERE returned_at IS NULL 将“检查”与“变更”合并为单一原子操作，天然满足幂等性，同时避免了 SELECT 后的竞态窗口。采纳，作为 NFR-1.3 的标准实现方式写入 ADR-002。

裁决 3：关于唯一索引的“诚实漏洞” —— 批准，并确认纳入阶段 3 验收

你的观察非常精准：④ 本人已持有 在同事务内拦截后，⑥ 唯一索引在正常业务路径上确实几乎不可达。但索引存在的意义是最后一道物理防线，用于防御代码 Bug、手动误操作或未来逻辑变更。因此，“绕过服务层直接 INSERT，断言抛 IntegrityError”的测试必须写入阶段 3 的故事验收标准，作为该索引存在的直接证据。 这是一条高质量的工程实践，请记录进 decision-log。

🚀 下一步指令
「所有裁决已给出，请执行：

将 ADR-004 中 [待验证] 的三处标注，按上述核查结果转正为 [已验证]，并附上验证来源（Werkzeug 3.0.0 changelog / Flask 3.1.0 release notes / PRAGMA journal_mode 返回值）。

将三处加严和“诚实漏洞”的测试要求写入对应 ADR 和 decision-log。

完成 ADR-006（物品模型） 和 ADR-007（状态机混合模型）。

全部写完后，运行最终的 Reviewer Gate 自检，确认 7 条 ADR 齐全、每条四段完整、否决备选理由充分。

自检通过后执行 git commit，阶段 2 正式锁定。」

关于你建议的“工作流隔离”：完全同意。 完成上述提交后，请开启新对话，携带 prd.md、decision-log.md、全部 7 条 ADR 以及 project-context.md，进入阶段 3（bmad-create-epics-and-stories）。阶段 3 中，NFR-1.3 的并发测试和唯一索引的“直接 INSERT”测试，必须作为独立故事或验收标准出现，不能只活在 ADR 里。

---

### [2026-11-08 15:15:03] **AI（assistant）**

已提交，工作树干净。

## 阶段 2（第 1 批）完成：ADR-001 ~ ADR-005

**两笔提交**：
- `c214c87` docs: add architecture ADRs 001-005 — 5 个文件，502 行
- `ea8ceaa` docs: fix playbook unique-index wording and log D-017~D-019

| ADR | 决定 | 否决的备选（数量） |
|---|---|---|
| [ADR-001 渲染方式](_bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/ADR-001-rendering.md) | Flask + Jinja2 SSR，单进程单端口，**无独立 API 层** | React SPA+REST（主）／fetch 渐进增强／Node+EJS — 3 条 |
| [ADR-002 并发唯一性](_bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/ADR-002-concurrency-uniqueness.md) | `item_id` 部分唯一索引 + `BEGIN IMMEDIATE` + 捕获 `IntegrityError`→409 | 先查后写／写锁当裁决者／`UNIQUE(user_id,item_id)`／`status='borrowed'` 裁决／额度事务外 — 5 条 |
| [ADR-003 会话](_bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/ADR-003-session.md) | Flask 签名 cookie session，明确接受「无法主动吊销」 | JWT／Flask-Session／自建 sessions 表／明文 cookie／进程内 dict — 5 条 |
| [ADR-004 密码存储](_bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/ADR-004-password-storage.md) | PBKDF2-SHA256，显式 `method=` | 明文／MD5·SHA1·单次 SHA256／自建加盐／bcrypt·Argon2／密码进 cookie — 5 条 |
| [ADR-005 并发与部署](_bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/ADR-005-concurrency-deployment.md) | WAL + `busy_timeout=5000` + 单进程 `python app.py` | 多 worker／rollback journal／PostgreSQL／应用层全局锁／ORM 隐式事务 — 5 条 |

**四条硬性要求自检**：四段齐全 ✓；否决备选 23 条、每条都写了理由 ✓；未改动 PRD 任何产品值（3 件 / 7 天 / 六步顺序原样引用）✓；decision-log 补 D-017~D-019 ✓。

**ADR-002 里三处我自主加严、请复核**：
1. `item_id` 外键**不用** `ON DELETE CASCADE` —— 级联会静默删掉在借记录，掩盖 FR-6 漏判；改为事务内显式删已归还记录，外键兜底「该响就响」。
2. 归还用**条件 UPDATE**（`WHERE returned_at IS NULL`）+ 判断 `rowcount`，而不是先查状态再更新 —— 直接对应 NFR-1.3。
3. **⚠ 一个诚实的漏洞**：④ 已在同事务内拦下重复借阅，所以 ⑥ 唯一索引在正常路径**几乎不会被触发**——「建了索引」这件事光靠黑盒并发测试是证明不了的。因此要求补一条「绕过服务层直接 INSERT，断言抛 `IntegrityError`」的测试，那才是索引存在的直接证据。这条建议会带进阶段 3 的故事验收。

**三处技术细节我没法核实，已标 `[待验证]` 而不是写成结论**（本机没装 Flask，网络检索报 API key 认证失败）：
- **Werkzeug 2.3 起 `generate_password_hash` 默认从 `pbkdf2:sha256` 改成 `scrypt`** —— 所以 ADR-004 强制显式传 `method`，并配一条「哈希串必须以 `pbkdf2:sha256:` 开头」的测试。这是我最没把握的一条，建议你顺手核一下。
- Python 3.14.7 下 Flask/Werkzeug 的兼容性（装不上就退回 3.12）。
- WAL 是否真的落盘（`PRAGMA journal_mode` 必须返回 `wal`）。

---

**下一步等你指令**：ADR-006（物品模型单件实体，D-001）与 ADR-007（状态机混合模型，D-015）我还没写，按你最初的节奏是逐条评审。要我接着写这两条吗？

另外提示：ADR-006/007 会被阶段 3 的故事直接引用，建议写完后紧接着开**新对话**做 `bmad-create-epics-and-stories`（工作流隔离）。

---
