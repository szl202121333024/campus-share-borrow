---
title: 'Story 2.4：NFR-1.2 同一用户并发超额——BEGIN IMMEDIATE 的事务原子性'
type: 'feature'
created: '2026-11-10'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '69253e3'
context:
  - _bmad-output/project-context.md
  - _bmad-output/planning-artifacts/epics.md#story-24
  - _bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/ADR-002-concurrency-uniqueness.md
  - decision-log.md（D-009、D-012、D-013、D-021、D-024、D-025）
---

# Story 2.4：NFR-1.2 同一用户并发超额

作为**产品负责人**，我希望有硬证据证明「一个还差 1 件满额的用户，同时借两件东西不会借到 4 件」。

## 范围裁决

- 与 Story 2.3 相互独立：2.3 考物品唯一索引，2.4 考用户额度 + `BEGIN IMMEDIATE`（epics 原文：两者不得合并；AC-2.4.4 白盒直测在本故事测试集**独立执行、独立计数**）。
- AC-2.4.5 为**反向证明**：同用户第 4 条（不同物品）直插必须被数据库接受——额度没有任何 DB 级兜底，只能靠写事务原子性。

## 实现（本轮实际改动）

1. **额度单点化重构（D-025，人类裁决方向落地）**：
   - `services/loans.py` 新增 `get_remaining_quota(student_id)`：函数体内仅一条 `COUNT(*) FROM loans WHERE user_id = ? AND returned_at IS NULL`，全项目额度计数 SQL 唯一真相（PC-7、AC-2.4.7）。
   - ④ 改为 `_active_loan_for_item()` 非聚合存在性查询（`SELECT user_id ... LIMIT 1`），⑤ 调用 `get_remaining_quota()`；两者仍同处 `borrow_item()` 的**同一个** `BEGIN IMMEDIATE` 写事务（D-009），自洽快照由事务串行化保证——D-008 意图不变，从未要求共用一条语句。
   - `test_loans.py` 同步：AC-2.1.9 断言改为 loans 读取 2 次、`COUNT(*)` 聚合恒 1 次；AC-2.1.10 结构定位改用新函数名；AC-2.1.6 ⑥ 兜底打桩改双函数替换。六步顺序与优先级矩阵（AC-2.1.8）、逐字一致（D-016）全部保持通过。
2. **脚手架共享化（用户指示"严格复用"）**：`tests/concurrency_kit.py` 提升 2.3 全套真并发机制（`start_threaded_server`、`race_post`、`login_over_http`、`direct_connect/direct_query` 等）；`test_concurrency.py` 改为导入 kit、仅保留薄包装 `race_borrow`。重构后 2.3 全量用例复跑通过。

## 测试（tests/test_quota_concurrency.py，8 条）

- AC-2.4.1~2.4.3：真实 threaded 服务器、同一用户会话经**两个独立 TCP 连接** barrier 对齐并发借**不同**物品，恰好 `{302, 409}`、409 方错误码恰好 `LIMIT_EXCEEDED`、未归还 COUNT 恰好 3，**20 轮**逐轮重置逐轮断言，无一例外；逐轮日志入库 `concurrency-nfr12-20-rounds.log`（*.log 精确豁免，同 SM-2 口径）。
- AC-2.4.4：D-021 白盒直测独立执行（同 item 重复在借直插 → `IntegrityError: UNIQUE constraint failed: loans.item_id`）。
- AC-2.4.5：反向证明——同用户 4 条不同物品直插**全部被接受**（COUNT=4 无异常），并断言 loans 上任何唯一索引均为 `item_id` 维度（不存在 user 维度唯一索引）。
- AC-2.4.6：`BEGIN IMMEDIATE` + `isolation_level=None` + 校验先于 INSERT + 全项目 `BEGIN DEFERRED` 0 命中。
- AC-2.4.7：全业务源码 `COUNT(*)`+`FROM loans` 扫描恰 1 处且位于 `get_remaining_quota` 函数体行范围内。
- AC-2.4.8：两用户并发各借（10 轮）→ 全部 302，写事务串行化不误拒。
- AC-2.4.9：LIMIT_EXCEEDED 失败前后 loans/items 全表逐字段一致。
- AC-2.4.10：管理员第 4 件同样 409 `LIMIT_EXCEEDED`；`services/loans.py` 检索 `\brole\b` 命中 0（D-012）。

## 规约自检（写码前重读 15 条）

PC-1 路由零业务判定（复用既有）；PC-2 连接唯一（kit 直连属 tests 豁免口径，同 2.3）；PC-4 写路径全走 `write_transaction()`；PC-5 六步顺序不变，重构仅拆 ④⑤ 查询形态；PC-7 额度单点（D-025）；PC-9 错误码同源；PC-13 snake_case（新函数 `get_remaining_quota`/`_active_loan_for_item`/`race_post` 等）；PC-14 中文文案不变。

## 验证结果

- `tests/test_quota_concurrency.py`：**8/8 通过**（39.06s）。
- 重构波及面复验：`test_loans.py` + `test_concurrency.py` 22/22 通过。
- 全量回归：**107 passed**（99→107，零回归）。

## 关联决策

- **D-024**（人类裁决，本故事前登记）：`IntegrityError` 精确映射升格为 **ADR-008**，ADR 索引/AGENTS.md/README 口径同步为「阶段 2 定稿 7 条 + 阶段 4 追加 1 条」。
- **D-025**（AI 识别规格张力，人类指示落地）：AC-2.4.7 与 AC-2.1.9 的实现级冲突以额度单点化重构解决，2.1 断言同步更新。

## 遗留

见 `deferred-work.md` Story 2.4 节：NFR-1.3 归还真并发直压建议、kit 的 `race_post` 仅覆盖 /borrow 形态。
