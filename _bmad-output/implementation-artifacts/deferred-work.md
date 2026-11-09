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
