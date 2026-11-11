# campus-share-borrow

校园共享器材 / 图书借阅系统 —— 研究生课程「AI 敏捷交付」作业。

> 状态：**五个阶段全部完成**（12/12 故事交付，Epic 1~3 收官；**202 个测试全绿**，含 10 组 200 轮真并发实验与 9 份逐轮证据日志；实验 A 对照实验已完成并写入 `retrospective.md`）。规划基线锁定：PRD `status: final`；ADR-001 ~ ADR-008（阶段 2 定稿 7 条 + 阶段 4 依 D-024 追加 1 条）；`epics.md` 定稿 3 史诗 / 12 故事 / 110 条 AC；`decision-log.md` 至 D-027。

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
- ≥5 条 ADR（每条写明「否决的备选」）→ 已产出 **8 条**（ADR-001~008，每条均有专节列出被否决的备选方案）
- `project-context.md`（≥8 条实现规则）→ 已产出 **15 条**（PC-1 ~ PC-15，每条可 `grep` 判定）
- `decision-log.md` ≥15 条 → 已产出 **27 条**（D-001 ~ D-027），其中人类实质否决 / 修改 AI 方案 **≥5 条**（D-002、D-003、D-004、D-022、D-024、D-025、D-026、D-027 等）
- 实验 A 对照实验 → **已完成**。实验组走 BMAD 交付 Story 3.1（添加物品）与 Story 2.2（归还，核心并发逻辑）；对照组仅凭一句「帮我写一个添加物品的功能」裸写同一需求。主对照段取**同需求**的 Story 3.1 vs 对照组（变量干净），Story 2.2 作为「架构前置收益为正」的佐证。结论与局限见 `retrospective.md`，对照组原始代码见 `docs/evidence/experiment-a/`

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

启动后访问 http://127.0.0.1:5000/items （匿名可读）。首次启动自动建库（`campus_share_borrow.sqlite` 单文件）并写入种子数据；删除该文件重启即回到初始状态。启动失败会打印一行中文原因并以非零码退出。用管理员账号（A001）登录后，`/admin/items` 提供物品新增、删除（有未归还记录时 409 拦截）、停用与恢复上架（两者均幂等，重复点击仍是 302 + 提示），以及含停用项的完整管理清单（Story 3.1~3.4；v1 无编辑功能，裁决见 decision-log）。

停用与恢复上架的口径（D-005、ADR-007）：停用可作用于**正在被借**的物品——借阅者在「我的借阅」里仍能看到并正常归还，归还只写借阅记录，物品保持停用直到管理员手动恢复；恢复上架后若该物品仍在别人手上，存储态为 `available`、页面展示仍派生出「在借」。

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
| 4 | `/bmad-sprint-planning` 取得 PASS，逐故事实施 | ✅ 完成（12/12 故事；Story 3.4 终局回归：四态组合矩阵 + NFR-1.4 并发交叉比对，证据见 [`spec-3-4`](_bmad-output/implementation-artifacts/spec-3-4-four-state-matrix-and-nfr14.md)） |
| 5 | 实验 A 对照实验 + `retrospective.md` | ✅ 完成（对照组原始代码与隔离条件见 `docs/evidence/experiment-a/`；结论见 `retrospective.md`） |

## 关键产物（已产出）

| 产物 | 路径 |
|---|---|
| PRD（final） | [`prd.md`](_bmad-output/planning-artifacts/prds/prd-campus-share-borrow-2026-11-08/prd.md) |
| 架构决策索引 + 8 条 ADR | [`README.md`](_bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/README.md) |
| 史诗与故事（3 史诗 / 12 故事 / 110 条 AC） | [`epics.md`](_bmad-output/planning-artifacts/epics.md) |
| 项目实现规约（15 条） | [`project-context.md`](_bmad-output/project-context.md) |
| 阶段 3 评审闸门证据（可复跑脚本 + 实测输出） | [`gate-stage3.md`](docs/evidence/gate-stage3.md) |
| Story 3.4 终局回归证据（四态矩阵 + NFR-1.4 交叉比对） | [`spec-3-4-four-state-matrix-and-nfr14.md`](_bmad-output/implementation-artifacts/spec-3-4-four-state-matrix-and-nfr14.md) |
| 并发实验逐轮证据日志（9 份，共 200 轮真并发） | `_bmad-output/implementation-artifacts/concurrency-*.log` |
| 决策日志（D-001~D-027） | [`decision-log.md`](decision-log.md) |
| 最终实验报告（学号 2601027150 / 宋志林） | [`2601027150-宋志林-元服务基础功能五实验报告.md`](2601027150-宋志林-元服务基础功能五实验报告.md) |
| 回顾与实验 A 结论 | [`retrospective.md`](retrospective.md) |

## AI 使用声明

本仓库的开发过程由 BMAD-Method v6 驱动，AI 承担方案产出，人类承担评审与否决。关键决策点全部留痕于 `decision-log.md`。

**过程凭证的形态（如实说明）**：本组以 [`docs/evidence/decision-evidence.md`](docs/evidence/decision-evidence.md) 中的**逐字对话摘录**作为过程凭证，未附对话面板截图。理由：摘录可 grep、可 diff、能同时固定「AI 说了什么 / 人类怎么驳 / 改成了什么」，比截图更难伪造；组内未保留截图，此点不掩饰。

## 规模裁剪（Process Tailoring）

按 BMAD 的三档裁剪刻度（档位名称以讲义为准），本项目取**最完整的一档**：四阶段全走 + 实验 A。理由两条：

1. 选题命中「有并发或一致性风险的功能点」这一门槛（两人同时借同一件物品），NFR-1 要求可执行断言，架构阶段无法靠抄技术栈清单糊过去；
2. 作业下限（5 条 ADR、12 个故事、110 条 AC、15 条实现规约）本身就要求完整走完规划链。

反向裁剪的部分：不做实验 B（作业已明令取消变更注入）；不做 TEA 与 bmb 模块（讲义列为加分项，非必需）。

## 裁剪的代价（复盘结论）

15 条实现规约中，真正**拦住过智能体**的是可被机械判定的那几条，而不是写得最漂亮的那几条：

| 规约 | 是否拦住过 | 证据 |
|---|---|---|
| PC-2（`sqlite3.connect` 仅在 `db.py`） | **是**，且拦住的是人类自己 | 阶段 5 把对照组代码以 `.py` 入库，该守卫立即报 2 failed，改证据后缀后复绿 |
| PC-3（蛇形命名） | **否** | 对照组在零规约下也写成 snake_case；此规约未产生区分度 |
| PC-9（真实 4xx，禁 200+错误文案） | **否** | 对照组校验失败同样返回真实 400，未出现 200 + 错误文案 |
| PC-10（授权判定唯一落点） | **部分是** | 经 D-026 人类加严后成为可扫描的结构断言（全库 `role != "admin"` 恰一处），但未记录到「先违规、再被拦下」的实例 |

诚实地说：四条里只有一条真正以"阻断"的形式起过作用，另外三条是**事前约束**，没有留下"没它就出事"的证据。这条结论对 BMAD 不利，但比反过来写好。
