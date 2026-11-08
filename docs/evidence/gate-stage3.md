---
title: 阶段 3 Reviewer Gate 证据
created: 2026-11-08
updated: 2026-11-08
phase: 3 / bmad-create-epics-and-stories
verifier: docs/evidence/verify_stage3_gate.py
verdict: PASS
---

# 阶段 3 · Reviewer Gate 证据

**被检对象**：`_bmad-output/planning-artifacts/epics.md`、`_bmad-output/project-context.md`

**复跑方式**（仓库根目录，无需安装额外依赖）：

```powershell
python docs/evidence/verify_stage3_gate.py   # 退出码 0 = 全部通过
```

## 1. 脚本输出（2026-11-08 实测，逐字粘贴）

```text
编号    检查项                                   结果
------------------------------------------------------------------------------
A-1   史诗数 = 3                               PASS  计数 = 3
A-2   故事数 = 12                              PASS  计数 = 12
A-3   每条 AC 均 Given/When/Then 且配对           PASS  AC 总数 = 110
A-4   NFR-1.1 / NFR-1.2 各自独立成故事             PASS  2.3 的 AC 只断言物品唯一性，2.4 的 AC 只断言额度不变量
A-5   D-021 白盒验收原文出现在两个并发故事中                PASS  2.3 = 1 次，2.4 = 1 次，全文 = 2 次
A-6   故事正文不含 PRD 非目标关键词                     PASS  0 命中
A-7   FR-1 ~ FR-6 全覆盖                       PASS  6/6
A-8   无前向依赖（只依赖更早的故事）                       PASS  12/12
A-9   epics.md / project-context.md 无占位符残留  PASS  0 命中
A-10  锁定值（3 件 / 7 天 / 错误码语义）存在且未被改写         PASS  限额 3、借期 7 天、六步顺序、错误码逐字引用
A-12  每个故事都标注规模与关联需求                        PASS  12/12
PC    project-context.md 规约 ≥ 8 条           PASS  计数 = 15
PC-3  第 3 条规约是 snake_case                   PASS  与评审手册驳点 4-2 的台词一致

结论：PASS —— 3 个史诗 / 12 个故事 / 110 条 AC，A-1 ~ A-12 全部通过。
```

## 2. 脚本覆盖不到的判定（人工复核）

| 编号 | 检查项 | 判定方式 | 结果 |
|---|---|---|---|
| A-11 | 每条 AC 归属唯一故事 | 逐条通读 110 条 AC，确认同一断言未在两个故事中重复出现 | ✅ 唯一；两条刻意复用处已登记为观察项 O-2 |
| A-8 补充 | 依赖是否指向**更早**的故事 | 脚本已机检 `Story N.M` 序号单调；本行补充人工确认跨史诗依赖只指向 Epic 1 | ✅ Epic 2 只依赖 Epic 1；Epic 3 只依赖 Epic 1 |
| A-13 | 故事是否「一个开发会话可完成」 | 逐故事核对「规模」字段与技术要点数量 | ✅ 12/12，无「一次性建全部表」「一次做完一个史诗」 |
| A-14 | 每条 AC 是否有可断言对象 | 抽样 12 条 AC，逐条确认含状态码/错误码/SQL 计数/PRAGMA/grep 之一 | ✅ 12/12 |

## 3. 观察项（交人类裁决，不阻塞阶段 3）

| 编号 | 观察 | 建议动作 |
|---|---|---|
| O-1 | PRD §4 可数出 **9** 个错误码，但 PRD/ADR-001/架构索引沿用「8 个错误码」的表述 | 阶段 4 订正措辞，或明确「8」不含 400 的 `INVALID_INPUT`；本阶段未擅自改 PRD（AGENTS.md §4） |
| O-2 | D-005 用例 A 在 Story 2.2 与 Story 3.3 各出现一次（用例 B 只在 Story 3.4） | 刻意保留：2.2 用 SQL 构造停用态以免 Epic 2 依赖 Epic 3；3.3 经管理接口端到端复验。两者独立执行、结论一致 |
| O-3 | FR-5 的「登录后 /items 显示限额指示」落在 Story 2.5 而非 Story 1.3 | 避免 1.3 前向依赖 Epic 2 的额度函数；1.3 先不渲染该区块，2.5 补齐 |

## 4. 结论

**PASS**。3 个史诗 / 12 个故事 / 110 条 Given-When-Then 验收标准；NFR-1.1 与 NFR-1.2 分属两个独立故事；D-021 的白盒验收（`IntegrityError` 直测）逐字出现在两个并发故事中；故事正文对 PRD 非目标 0 命中；无前向依赖；无占位符。
