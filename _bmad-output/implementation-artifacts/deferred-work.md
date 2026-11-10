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
