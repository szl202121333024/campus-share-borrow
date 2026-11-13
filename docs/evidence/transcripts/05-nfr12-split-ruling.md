# 对话摘录 · 决策点 · 人类裁决 NFR-1.1 / NFR-1.2 必须拆成两个独立并发故事

> 来源：DSH NEXT 本地会话转录（`C:\Users\honor\.dsh\sessions\--D-documents-homework--\` 下 `session.v4.jsonl.zstd`），
> 由脚本原文导出：未改写任何对话文字，超长消息在截断处标注「（后略，共 N 字）」。
> 会话 ID：`session-9a1aec7a-c8be-43a6-bbba-d6e51ab6a31f` · 会话创建：2026-11-08 14:11:16 · 模型：`deepseek (see raw jsonl)` · 工作区：`D:\documents\homework`

---

### [2026-11-08 14:46:37] **人类（user）**

⚖️ 裁决 1：关于“不能编辑物品”（同意）
台词：「我同意你的判断，FR-6 不支持编辑物品。
理由：结合 D-007（砍掉历史视图和快照），如果在列表里允许改名，旧借阅记录里的物品名称就会发生“漂移”，这严重违反了 NFR-2（数据一致性）。没有快照机制就不配做编辑功能。
如果管理员发现名字录错了，正确的操作是：先删除（如果无在借），重新新建。把这个作为一条业务规则写进 Notes 里。」

⚖️ 裁决 2：关于 NFR-1.2 拆分（必须拆）
台词：「绝对要拆成独立故事。
理由：NFR-1.1（防同一物品超卖）是数据库唯一索引的功劳；而 NFR-1.2（防同一用户超额）是 BEGIN IMMEDIATE 写事务的功劳。这两者测的是完全不同的底层机制。如果不拆，AI 极容易在实施阶段只写个唯一索引，就把额度校验做成“先查后写”直接糊弄过去。拆出来，并在测试用例里明确写死『必须跑并发测试验证 D-009』。」

⚖️ 裁决 3：关于“启动命令”的表述（改为与技术栈无关）
台词：「采纳你的建议，改成技术栈无关的表述。
理由：现在还在 PRD 阶段，我们应当定义『是什么』，而不是『怎么做』。把 NFR-2 里的命令改成：『提供唯一且清晰的启动命令（如 npm start 或 python app.py），并在 README 中明确声明，确保单条命令启动。』 这样既守住了“一条命令启动”的底线，又不会限制阶段 2 的架构选型。」

🚀 最终指令：PRD 收尾与 Reviewer Gate
「裁决完毕，请按照以上三条修改。接下来，一次性写完剩下的 §7 MVP范围、§8 成功度量（包含反向指标）、§9 开放问题、§10 假设索引。

注意：

§8 反向指标必须写明：如果并发测试（NFR-1.1/1.2）没跑通，或者发现用了先查后写，直接判定项目核心失败。

全部写完后，自己跑一遍 Reviewer Gate（对照所有 FR/NFR 是否有遗漏）。

确认无误后，执行 git commit -m "docs: add PRD"。」

---

### [2026-11-08 14:46:37] **人类（user）**

Time sampled while preparing turn 9, step 1: 2026-11-08T14:46:37+08:00[Asia/Shanghai]
Browser time zone for this request: Asia/Shanghai. Interpret otherwise-unqualified dates and times in this zone.
Elapsed since the preceding model-visible message: 2m 22s.

---
