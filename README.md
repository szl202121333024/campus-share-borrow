# campus-share-borrow

校园共享器材 / 图书借阅系统 —— 研究生课程「AI 敏捷交付」作业。

> 状态：**阶段 0 待启动**（仓库与目录骨架已就位，BMAD-Method v6 流程尚未开始）。

## 项目基线（锁定，不再发散）

| 项 | 内容 |
|---|---|
| 项目名称 | 校园共享器材 / 图书借阅系统 |
| 核心业务 | 登录、浏览、借阅、归还、管理员增删 |
| 核心并发风险 | 两人同时借阅同一件物品，只能一人成功，另一人收到冲突提示 |
| 技术栈 | SQLite 单文件库 + 服务端渲染（Flask + Jinja2），**禁止前后端分离** |

## 硬性约束

- 工作流隔离：一个工作流 = 一个新对话；切换前须提示「请开新对话」。
- 不做实验 B（已取消变更注入）。
- 产物目录：`_bmad-output/planning-artifacts/`、`_bmad-output/implementation-artifacts/`。
- 根目录必须有 `decision-log.md` 与 `retrospective.md`。

## 产物底线

- 3 个史诗（≥12 个故事）
- ≥2 条 NFR
- ≥5 条 ADR（每条写明「否决的备选」）
- `project-context.md`（≥8 条实现规则）
- `decision-log.md` ≥15 条，其中 ≥5 条为人类实质否决 / 修改 AI 方案
- 实验 A 对照实验（实验组：BMAD 走故事 2.2 归还；对照组：裸写故事 3.1 管理员添加物品）

## 目录结构

```
.
├── README.md
├── decision-log.md
├── retrospective.md
└── _bmad-output/
    ├── planning-artifacts/        # PRD、架构、史诗与故事
    └── implementation-artifacts/  # 实施阶段产物
```

## 执行计划

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | `npx bmad-method install` + `/bmad-help` | 未开始 |
| 1 | `/bmad-prd`：FR-1~FR-6、NFR-1~NFR-2、明确不做 | 未开始 |
| 2 | `/bmad-architecture`：5 条 ADR（含两次诱导否决） | 未开始 |
| 3 | `/bmad-create-epics-and-stories`：≥12 故事 + `project-context.md` | 未开始 |
| 4 | `/bmad-sprint-planning` 取得 PASS，逐故事实施 | 未开始 |
| 5 | 实验 A 对照实验 + `retrospective.md` | 未开始 |

## AI 使用声明

本仓库的开发过程由 BMAD-Method v6 驱动，AI 承担方案产出，人类承担评审与否决。
关键决策点全部留痕于 `decision-log.md`，对话截图作为过程凭证。
