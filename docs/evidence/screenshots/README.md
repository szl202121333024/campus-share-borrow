# 截图证据 · 决策点对话（transcript render）

> **性质说明（诚实声明）**：本目录中的图片**不是原始应用界面的截图**，
> 而是脚本从本地会话转录（DSH NEXT 工作区 `D:\documents\homework` 的
> `~/.dsh/sessions/--D-documents-homework--/session-*.v4.jsonl.zstd`，路径见各摘录文件）
> 中导出的**原文渲染图**：对话文字未做任何改写，仅按时间顺序重排并标注来源。
>
> 每张图对应的文字版摘录在 [`../transcripts/`](../transcripts/)（含会话 ID、时间戳、模型信息）。
> 原始对话面板截图因当时未保存而缺失，特此如实说明。

| 文件 | 决策点 | 对应记录 |
|---|---|---|
| `transcript-render-01-react-veto-adr001.png` | AI 起草 React 方案 → 人类坚决否决，改 SSR | ADR-001 · D-017 |
| `transcript-render-02-unique-index-adr002.png` | AI 指出手册唯一索引挡不住超卖 → 人类授权改为 item_id 部分唯一索引 | ADR-002 · D-018 / D-021 |
| `transcript-render-03-six-step-D016.png` | AI 发现 D-006 与 D-008 互相矛盾 → 提出六步判定顺序 → 人类裁决锁定 | D-016 |
| `transcript-render-04-story-scope-guard.png` | 人类死命令三条（范围/拆分/白盒）→ AI 候选 18 个故事驳回至 12 个 | 强制决策点 3 |
| `transcript-render-05-nfr12-split-ruling.png` | 人类裁决 NFR-1.1 / NFR-1.2 必须拆成独立并发故事 | 强制决策点相关 |
| `transcript-render-06-experiment-a-design.png` | 实验 A 对照组设计；「100% 超卖」预测未实测，AI 如实降级为结构推断 | D-027 |
