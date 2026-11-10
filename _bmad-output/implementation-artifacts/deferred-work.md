# Deferred Work

This file tracks work items that were identified during implementation but deferred to future stories or iterations.

---

## Story 1.2: 学号登录、登出与会话访问控制

- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-login-logout-session-access-control.md`
  summary: CSRF/brute-force/clickjacking protection
  evidence: PRD §6「不做登录锁定」隐含不接受暴力破解防护作为 v1 范围；CSRF 防护属 PRD 明确不做的安全增强项（PRD SM-C2：不过度抽象）。记录到 deferred-work，不阻塞本故事。

- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-login-logout-session-access-control.md`
  summary: session["login_at"] dead data
  evidence: 可能用于未来审计日志或绝对过期计算（vs idle expiry），暂留作技术债。不在 v1 范围内强制使用。

- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-login-logout-session-access-control.md`
  summary: Doc drift (sprint-status.yaml header comments)
  evidence: sprint-status.yaml 的头部注释 "Readiness gate：PASS""下一动作" 是阶段信息而非运行时状态，每次新故事完成后更新一次即可，不是实时校验指标。

---

## Story 2.1: 借阅物品（六步判定与应还日期）

- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-borrow-item-six-step.md`
  summary: CSRF/brute-force/clickjacking protection
  evidence: 沿用 Story 1.2 已裁决的延期口径（PRD §6 明确不做）。POST /borrow 写路径同样不带 CSRF token；v1 局域网单人演示场景接受该风险，记录不阻塞。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-borrow-item-six-step.md`
  summary: 并发冒烟 ≠ NFR-1.1 正式验收
  evidence: test_borrow_concurrency_smoke 用 test_client + barrier 验证机制可用（20 轮恰一成功一冲突）；正式 20 轮真并发（线程 + 独立连接 + sqlite3 直连）与 D-021 白盒直测仍属 Story 2.3，不得以此冒烟替代。

---

## Story 2.2: 归还物品（条件 UPDATE、停用物品保持停用）

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-return-item-conditional-update.md`
  summary: CSRF 保护（POST /return 写路径）
  evidence: 沿用 Story 1.2/2.1 已裁决口径（PRD §6 明确不做）。归还写路径同样不带 CSRF token，记录不阻塞。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-return-item-conditional-update.md`
  summary: AC-2.2.9 冒烟 ≠ NFR-1.3 正式验收
  evidence: test_ac_2_2_9_concurrent_return_one_success_one_conflict 用 test_client + barrier 双会话 20 轮，验证条件 UPDATE + rowcount 的机制连通；NFR-1.3 的独立进程/独立连接直压验收随 Story 2.3 的并发脚手架一并补齐，不得以此冒烟替代。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-return-item-conditional-update.md`
  summary: /my-loans 仅最小可用版
  evidence: 本故事按 epics.md「规模」条款实现归还入口 + 逾期标红 + is_overdue 单 SQL 派生；额度指示与完整版在 Story 2.5（额度只有一处真相）收口。停用状态以直接 SQL 构造系本故事技术要点明确授权，管理员停用入口属 Story 3.3。

---

## Story 2.3: NFR-1.1 同一物品并发借阅（部分唯一索引物理兜底）

- source_spec: `_bmad-output/implementation-artifacts/spec-2-3-nfr11-concurrent-borrow.md`
  summary: NFR-1.3 归还真并发直压仍待补
  evidence: Story 2.2 的 20 轮双会话冒烟已证机制连通；本故事已交付真实 threaded 服务器脚手架（start_threaded_server + race helper），归还直压验收建议在 Story 2.4 复用同一脚手架补齐，不得继续只靠 test_client 冒烟。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-3-nfr11-concurrent-borrow.md`
  summary: 测试脚手架行为非产品功能
  evidence: 20 轮间以底层 SQL 标记归还做重置、以及用连接层替身注入 FOREIGN KEY 失败（AC-2.3.10），均为 tests/ 内脚手架；生产代码路径不受影响，评审时不要当作产品能力。

---

## Story 2.4: NFR-1.2 同一用户并发超额（BEGIN IMMEDIATE 事务原子性）

- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-nfr12-concurrent-quota.md`
  summary: CSRF 保护（并发实验经真实 HTTP 表单提交）
  evidence: 沿用 Story 1.2 起已裁决的延期口径（PRD §6 明确不做）。kit 的 race_post 走真实 TCP 提交表单同样不带 CSRF token，风险口径不变，记录不阻塞。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-nfr12-concurrent-quota.md`
  summary: NFR-1.3 归还真并发直压仍待补
  evidence: Story 2.3 遗留项继续有效。本故事的 threaded 脚手架已可直接支撑归还并发（race_post 目前只封装 POST /borrow 形态，需扩展或新写 race_post_return），建议结合 Story 2.5 的额度指示收口一并补齐；不得继续只靠 2.2 的 test_client 冒烟充当正式验收。
  **RESOLVED (Story 2.5)**：kit 已泛化 race_request 并新增 race_return；tests/test_return_concurrency.py 以真并发 20 轮 {302,409} + returned_at 单次写入完成正式验收，逐轮日志 concurrency-nfr13-return-20-rounds.log 入库。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-nfr12-concurrent-quota.md`
  summary: get_remaining_quota() 页面调用方尚不存在
  evidence: 额度单点化重构（D-025）已把「借阅前置校验」接入唯一真相；「页面限额指示」调用方（/items 与 /my-loans 顶部「已借 X / 3」）按 epics 条款属 Story 2.5（AC-2.5.3/2.5.5），本故事不提前渲染。

---

## Story 2.5: 我的借阅与限额指示（额度只有一处真相）

- source_spec: `_bmad-output/implementation-artifacts/spec-2-5-my-loans-quota-indicator.md`
  summary: 20 轮证据日志被每次测试重写，优化留待项目收尾
  evidence: concurrency-nfr11/nfr12 两份日志由用例无条件覆写（仅时间戳变化）。用户 2026-11-10 指示：不着急，整个项目跑完再优化；候选方案为 conftest.py 增加「已存在则不覆盖」判断，或只保留首轮样本作为只读证据。三处写盘点：tests/test_concurrency.py、tests/test_quota_concurrency.py、tests/test_return_concurrency.py。
