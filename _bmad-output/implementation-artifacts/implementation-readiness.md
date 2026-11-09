---
title: 阶段 4 实施就绪与 Sprint 计划
created: 2026-11-09
updated: 2026-11-09
phase: 4 / bmad-sprint-planning
verdict: PASS
next_action: bmad-build Story 1.2
---

# 阶段 4 实施就绪与 Sprint 计划

## Gate 结论

**PASS**。实现所需的需求、架构、故事拆分和代码规约已经足够完整，开发者可以按故事实施而无需自行发明未记录的产品或架构决策。

核验依据：

- `docs/evidence/gate-stage3.md` 已证明 3 个 Epic、12 个故事、110 条 Given/When/Then AC 通过阶段 3 gate。
- `_bmad-output/planning-artifacts/prds/prd-campus-share-borrow-2026-11-08/prd.md` 已锁定限额 3 件、借期 7 天、借阅六步判定、9 个错误码及 NFR-1.1~NFR-1.5。
- `_bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/README.md` 及 ADR-001~007 已记录渲染、会话、密码、SQLite 并发、物品模型和状态机决策，并明确否决方案。
- `_bmad-output/project-context.md` 提供 15 条可检验实现规约，覆盖目录分层、事务、唯一索引、归还、额度、状态派生、错误响应、测试和提交纪律。
- `decision-log.md` 的 D-022、D-023 已锁定 12 故事上限、并发故事拆分和 9 个错误码口径。
- 当前 HEAD `c747433` 已包含 Story 1.1 实现与测试；本次规划将其标为 `done`，下一项为 Story 1.2。

## 实施顺序

| 顺序 | 故事 | 依赖 | 实施边界 | 主要验证 |
|---:|---|---|---|---|
| 1 | Story 1.1：一条命令启动、自动建表与种子数据 | 无 | 已完成；保留现有自举、schema、种子数据和基础测试 | `pytest tests/test_bootstrap.py -v`；PRAGMA、部分唯一索引、CHECK 约束 |
| 2 | Story 1.2：学号登录、登出与会话访问控制 | 1.1 | 登录表单、Flask session、统一守卫、登出和错误响应 | 匿名重定向、错误凭据、学生/管理员角色、登出后的访问 |
| 3 | Story 1.3：物品列表与关键字搜索 | 1.1、1.2 | 学生端 SSR 列表、搜索参数、状态和当前借阅人展示 | 匿名可读、搜索命中、停用项隐藏、无结果、无 N+1 |
| 4 | Story 2.1：借阅物品（六步判定与应还日期） | 1.1、1.2、1.3 | 借阅服务与 POST 路由，固定六步顺序，借期使用常量 | 302/404/409 分支、7 天 due_at、失败无副作用 |
| 5 | Story 2.2：归还物品（条件 UPDATE、停用物品保持停用） | 2.1、1.1 | 只更新 loans，条件 UPDATE + rowcount，归还幂等 | 本人/他人/重复归还、并发归还、停用状态不回弹 |
| 6 | Story 2.3：NFR-1.1 同一物品并发借阅 | 2.1 | 20 轮真并发测试和 D-021 白盒索引直测 | 恰好 1 成功、1 冲突、在借记录 1 条、直接 INSERT 抛 `IntegrityError` |
| 7 | Story 2.4：NFR-1.2 同一用户并发超额 | 2.1、2.3 | `BEGIN IMMEDIATE` 覆盖额度检查与写入，独立于物品唯一性故事 | 20 轮恰好 1 成功、1 `LIMIT_EXCEEDED`、在借数不超过 3 |
| 8 | Story 2.5：我的借阅与限额指示 | 2.1、2.2 | 当前在借列表、逾期展示、复用 `get_remaining_quota()` | 额度实时释放、停用物品仍可归还、额度查询单一真相 |
| 9 | Story 3.1：管理员新增物品与管理列表 | 1.2、1.3 | 管理员权限、SSR 表单、名称/类别校验、全量管理列表 | 403/302、边界长度、重复名称、停用项和在借人展示 |
| 10 | Story 3.2：删除物品（在借拦截与同事务级联清理） | 3.1、1.1 | 事务内清理已归还 loans 后删除 items；不使用外键级联 | 在借 409、历史清理、异常回滚、GET 不删除 |
| 11 | Story 3.3：停用物品（在借也能停用，归还后仍停用） | 3.1、1.3 | 管理员唯一入口写 `items.status='unavailable'` | 学生端隐藏、借阅记录保留、可归还、停用幂等 |
| 12 | Story 3.4：恢复上架与状态机边界回归 | 3.3、1.3 | 恢复动作、派生态收敛、四种状态组合回归 | `UPDATE items` 仅两处、状态优先级、恢复后在借仍显示派生态 |

## 执行约束

- 每次只实现一个故事；下一项是 Story 1.2，应使用 `bmad-build`。
- 实现前读取 `AGENTS.md`、`project-context.md`、对应故事、相关 ADR；实现后按该故事 AC 与 PC 规约验证。
- NFR-1.1、NFR-1.2 和 D-021 白盒索引测试是项目一票否决路径，不能用串行测试替代。
- 本次仅生成规划产物，没有修改业务代码、测试代码或已锁定的规划基线。

## 生成说明

BMAD v6.12.4 的 `sprint_plan.py` 对 Epic/Story 标题使用英文冒号格式匹配；本仓库使用带数字前缀的中文全角冒号标题。因此本次按同一模板字段和合法状态执行手工生成，并以 `epics.md` 的 12 个标题逐项核对，避免为适配脚本而改写阶段 3 基线。
