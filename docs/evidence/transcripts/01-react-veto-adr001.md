# 对话摘录 · 决策点 1 · 人类否决 React 方案（ADR-001 / D-017）

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

### [2026-11-08 15:11:52] **AI（assistant）**

裁决收到。执行：ADR-001 改 SSR，ADR-002/003 按你的授权方案写，ADR-004/005 一并产出，改 playbook，记 decision-log，然后 commit。

写 ADR-004 前先核一件事——`generate_password_hash` 的默认算法已经不是 PBKDF2 了，我不能把未经核实的算法写进 ADR：

---
