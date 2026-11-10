---
id: ADR-008
title: IntegrityError 精确映射——仅唯一约束冲突可伪装为业务冲突
status: accepted
created: 2026-11-10
updated: 2026-11-10
deciders: [人类（产品负责人，Story 2.3 验收时裁决）, AI 工程师]
decision_log: [D-024]
related: [FR-3, NFR-1.1, NFR-2, ADR-002]
---

# ADR-008 · `IntegrityError` 精确映射：唯一约束之外的完整性错误原样上抛

**决定：借阅写路径捕获 `sqlite3.IntegrityError` 后，仅当异常消息命中部分唯一索引冲突特征串（`UNIQUE constraint failed: loans.item_id`）时，才映射为 409 `ALREADY_BORROWED`；其余完整性错误（外键失败、CHECK 失败等）一律原样上抛，由 Flask 呈现 500。**

## 1. 背景

Story 2.1 初版实现（D-016 ⑥ 兜底）对所有 `IntegrityError` 无差别映射 409「该物品已被借出」。Story 2.3 编写 AC-2.3.10 白盒测试时发现该写法会把外键失败等**真实底层 bug** 伪装成正常业务冲突：评审人看到 409 会认为是并发抢借，而实际是数据完整性损坏，故障被静默吞掉（违反 ADR-002 §4 的分工声明与 NFR-2「结构清晰、问题可观测」）。人类在产品负责人验收 Story 2.3 时确认修正并指示升格为独立 ADR。

## 2. 决定

- `services/loans.py::borrow_item()` 的 ⑥ 兜底分支：先比对 `_UNIQUE_ITEM_CONFLICT` 特征串，命中才抛 `BizError(409, ALREADY_BORROWED)`；未命中 `raise` 原样上抛。
- 特征串为模块级常量，与 ADR-002 锁定的索引定义（`ux_loans_active_item`）逐字对应；索引若改名，测试与常量同步失败，不会静默漂移。
- 出口侧行为：真实 `threaded` 服务器上注入外键错误，HTTP 返回 **500** 且响应体不含 `ALREADY_BORROWED`（测试 `test_ac_2_3_10_http_presents_500_not_409` 固化该口径）。

## 3. 否决的备选方案

1. **无差别捕获全部 `IntegrityError` → 409**：即 Story 2.1 初版。否决理由：掩盖真实 bug，违反 ADR-002 §4「索引只做唯一性兜底，不承担其他完整性语义」与 NFR-2 可观测性；正是本 ADR 要修正的对象。
2. **按异常类型细分（如 `sqlite3.OperationalError` 单独处理）**：否决理由：`IntegrityError` 内部各成因同为该类型，类型粒度不够，必须按消息特征串判定；细分类型反而制造假精确。
3. **为外键失败新增第 10 个错误码（如 `DB_INTEGRITY_ERROR`）**：否决理由：错误码集合由 PRD §4 锁定为 9 个（D-023 订正后口径），外键失败属程序 bug 而非用户可恢复的业务状态，为其发明业务错误码是把 bug 合法化；500 + 服务器日志才是正确出口。
4. **捕获后记录日志再返回 409「系统繁忙」**：否决理由：对用户谎报故障性质（看似可重试的业务冲突，实为数据损坏），且引入日志系统违背单文件 SQLite 的极简部署（ADR-005）。

## 4. 后果

- **正面**：唯一约束兜底（业务正常）与完整性损坏（程序 bug）在 HTTP 层可区分（409 vs 500）；AC-2.3.10 两条测试（服务层上抛断言 + 真实服务器 500 断言）成为回归防线；D-016「⑥ 与 ④ 逐字一致」语义保留——仅指唯一索引冲突这一种。
- **代价**：特征串与 SQLite 错误消息文案耦合，SQLite 大版本若改写措辞需同步更新常量（已用测试 `test_ac_2_3_4`/`test_ac_2_4_4` 白盒锚定：消息断言与常量同串，改则必红）。
- 本 ADR 不改变「⑥ 正常路径几乎不可达」的定位（D-021），只收窄其伪装范围。
