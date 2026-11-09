# campus-share-borrow

校园共享器材 / 图书借阅系统 —— 研究生课程「AI 敏捷交付」作业。

> 状态：**阶段 3 已完成并锁定**（PRD `status: final`；ADR-001 ~ ADR-007 定稿；`epics.md` 定稿 3 史诗 / 12 故事 / 110 条 AC）。下一步阶段 4：`bmad-sprint-planning` 取 PASS 后逐故事实施（需开新对话）。

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

- 3 个史诗 / **12 个故事**（不多不少，上限由 D-022 锁定）→ 已达标（Epic 1 认证与浏览 3 + Epic 2 借阅归还与并发 5 + Epic 3 管理员 4）
- ≥2 条 NFR → 已达标（NFR-1、NFR-2，可测）
- ≥5 条 ADR（每条写明「否决的备选」）→ 已产出 **7 条**（ADR-001~007，共 33 个否决备选）
- `project-context.md`（≥8 条实现规则）→ 已产出 **15 条**（PC-1 ~ PC-15，每条可 `grep` 判定）
- `decision-log.md` ≥15 条（截至阶段 2 已 **21 条**，其中人类实质否决 / 修改 AI 方案 **13 条**，≥5 已达标）
- 实验 A 对照实验（实验组：BMAD 走故事 2.2 归还；对照组：裸写故事 3.1 管理员添加物品）

## 目录结构

```
.
├── README.md
├── AGENTS.md                    # 仓库级工作约定（提交纪律、禁用值、留痕规则）
├── decision-log.md
├── retrospective.md
├── docs/                        # 输入材料（作业要求、评审手册、决策证据）
└── _bmad-output/
    ├── planning-artifacts/      # PRD、架构（ADR）、史诗与故事
    │   ├── prds/
    │   └── architecture/
    └── implementation-artifacts/  # 实施阶段产物
```

## 快速开始（唯一启动命令）

```bash
pip install -r requirements.txt
python app.py
```

启动后访问 http://127.0.0.1:5000/items （匿名可读）。首次启动自动建库（`campus_share_borrow.sqlite` 单文件）并写入种子数据；删除该文件重启即回到初始状态。启动失败会打印一行中文原因并以非零码退出。

测试：`python -m pytest tests/ -v`

### 种子账号

| 角色 | 学号 | 密码 |
|---|---|---|
| 学生 | 2024001 | stu123456 |
| 学生 | 2024002 | stu123456 |
| 管理员 | A001 | admin123456 |

### 已知限制

- 会话为无状态签名 cookie：直接重放登出前保存的 cookie 副本在 24 小时窗口内仍可能有效，服务端无法主动吊销（D-019，如实记录）。

## 执行计划

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | `npx bmad-method install` + `/bmad-help` | ✅ 完成（v6.12.4） |
| 1 | `/bmad-prd`：FR-1~FR-6、NFR-1~NFR-2、明确不做 | ✅ 完成（`prd.md` `status: final`；决策 D-001~D-016） |
| 2 | `/bmad-architecture`：ADR（含两次诱导否决） | ✅ 完成（**ADR-001 ~ ADR-007**；决策 D-017~D-021） |
| 3 | `/bmad-create-epics-and-stories`：3 史诗 / 12 故事 + `project-context.md` | ✅ 完成（`epics.md` 定稿；决策 D-022；Gate 证据 `docs/evidence/gate-stage3.md`） |
| 4 | `/bmad-sprint-planning` 取得 PASS，逐故事实施 | 未开始（**请开新对话**） |
| 5 | 实验 A 对照实验 + `retrospective.md` | 未开始 |

## 关键产物（已产出）

| 产物 | 路径 |
|---|---|
| PRD（final） | [`prd.md`](_bmad-output/planning-artifacts/prds/prd-campus-share-borrow-2026-11-08/prd.md) |
| 架构决策索引 + 7 条 ADR | [`README.md`](_bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/README.md) |
| 史诗与故事（3 史诗 / 12 故事 / 110 条 AC） | [`epics.md`](_bmad-output/planning-artifacts/epics.md) |
| 项目实现规约（15 条） | [`project-context.md`](_bmad-output/project-context.md) |
| 阶段 3 评审闸门证据（可复跑脚本 + 实测输出） | [`gate-stage3.md`](docs/evidence/gate-stage3.md) |
| 决策日志（D-001~D-022） | [`decision-log.md`](decision-log.md) |

## AI 使用声明

本仓库的开发过程由 BMAD-Method v6 驱动，AI 承担方案产出，人类承担评审与否决。
关键决策点全部留痕于 `decision-log.md`，对话截图作为过程凭证。
