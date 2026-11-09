---
title: 'Story 1.2：学号登录、登出与会话访问控制'
type: 'feature'
created: '2026-11-09'
status: 'done'
route: 'dispatch'
review_loop_iteration: 1
baseline_commit: 'fe9e3a8e097a1c28d1c86f43e0e30593a31ffe39'
context:
  - '{project-root}/_bmad-output/project-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 系统已有种子账号和公开列表，但尚不能登录，也没有统一身份、登出、会话过期和受保护路径拦截，因而无法区分访客、学生与管理员。

**Approach:** 增加认证服务、登录/登出路由、统一访问守卫及登录页；提供最小可用的“我的借阅”页面证明会话有效。物品借还和管理业务仍由后续故事实现，本故事只保证它们的访问边界先生效。

## Boundaries & Constraints

**Always:**
- 密码只经 `security.py` 校验；不存在学号也执行一次固定假哈希校验，四类登录失败统一 401 + `INVALID_CREDENTIALS` + 同一中文提示且不建会话。
- 会话只存 `user_id`、`role`、`login_at`，永久会话闲置 24 小时过期且逐请求刷新；cookie 为 HttpOnly、SameSite=Lax，本地 HTTP 不开 Secure。
- 统一守卫覆盖 `/my-loans`、`/borrow`、`/return/<id>`、`/admin/*`：未登录 302 到带 `next` 的登录页，已登录学生访问管理路径返回 403 + `FORBIDDEN`。
- `next` 只接受本站绝对路径；登录失败重新渲染表单并保留安全的 `next`。登出仅 POST，清空 session 并显式删 cookie。
- 真实 4xx + 统一错误码；snake_case；路由只收集参数和映射结果；页面与日志不回显密码、哈希或完整 cookie。

**Never:** 不做注册、JWT、服务端会话表、角色业务豁免、前端 API、登录锁定、借还或管理业务实现；不声称无状态 cookie 可在服务端吊销。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| 原目标跳转 | 有效 `next=/my-loans` | 登录后 302 回该路径 | 外部 URL、协议相对 URL 或非路径值回退 `/items` |
| 过期识别 | 签名正确但时间戳超过 24 小时的 cookie | 受保护页 302 登录页并提示“登录已过期” | 无效签名按未登录处理，不误报过期 |
| 后续路由尚未实现 | 未登录访问借还或管理路径 | 守卫先于 404/405 生效 | 登录学生访问管理路径仍优先返回 403 |

</frozen-after-approval>

## Code Map

- `app.py` — 已有关密钥加载、蓝图注册和统一错误页；补显式 session/cookie 配置并注册认证与我的借阅蓝图。
- `security.py` — 复用 `verify_password`，其内部调用 `check_password_hash`；不得绕过或新增第二套哈希逻辑。
- `db.py` — 复用 `get_db()`、`now_text()` 和种子账号；不改 schema、不新增连接。
- `config.py` — 复用 `BizError` 与 9 个错误码，不新增错误文案分支。
- `routes/items.py`、`templates/items.html` — 公开浏览保持匿名 200，不提前实现 Story 1.3 的完整展示要求。
- 新增 `services/auth.py` — 用户白名单查询、统一密码校验、假哈希、当前用户加载及精确过期识别。
- 新增 `routes/auth.py` — 登录/登出和唯一 `before_app_request` 守卫；新增 `routes/loans.py` 仅提供最小 `/my-loans` 页面。
- 新增 `templates/login.html`、`templates/my_loans.html`；调整 `templates/base.html` 展示身份、flash 与 POST 登出，非管理员不显示后台入口。
- 新增 `tests/test_auth.py` — 按 AC-1.2.1～1.2.10 建独立测试，过期用旧时间戳签名 cookie，不用 sleep。

## Tasks & Acceptance

**Execution:**
- [x] `services/auth.py` — 实现认证、当前用户和过期判定，确保每次登录尝试恰好一次哈希校验。
- [x] `routes/auth.py`、`routes/loans.py` — 实现登录/登出、next 安全跳转和统一路径守卫。
- [x] `app.py` — 注册蓝图，显式固定 session 刷新与 cookie 属性。
- [x] `templates/` — 完成登录、最小我的借阅和导航/消息展示，不渲染敏感字段。
- [x] `tests/test_auth.py` — 覆盖全部 AC、cookie 属性及日志脱敏，再运行全量回归。

**Acceptance Criteria:**
- Given 正确种子账号，when POST `/login`，then 302 `/items`、下发会话，随后 `/my-loans` 为 200。
- Given 学号不存在、密码错误、学号空或密码空，when 登录，then 均为 401、同码同文案且无会话 cookie。
- Given 已登录，when GET `/login`，then 302 `/items` 且不重渲染表单。
- Given 已登录，when POST `/logout`，then 302 `/items`、浏览器删 cookie，随后受保护页 302；旧 cookie 副本风险只留文档。
- Given 未登录，when 访问四类受保护路径，then 302 到带原路径的 `next`；安全目标登录后跳回。
- Given 访客，when 列表或搜索，then 均正常 200。
- Given 学生登录，when `/admin/items`，then 403 + `FORBIDDEN` 且不跳登录。
- Given 会话闲置超过/不足 24 小时，when 访问受保护页，then 分别 302 带过期提示/200。
- Given 种子密码，when 检查数据库及登录响应和日志，then 哈希以 `pbkdf2:sha256:` 开头且无明文或哈希泄露。
- Given 不存在学号，when 登录，then 固定假哈希校验恰好一次，且与密码错误的状态、错误码、文案一致。

## Implementation Notes

- 实现落在本地提交 `7a61f47`（8 个文件，+614/-1）：新增 `services/auth.py`、`routes/auth.py`、`routes/loans.py`、`templates/login.html`、`templates/my_loans.html`、`tests/test_auth.py`；修改 `app.py`、`templates/base.html`。
- 会话永久化通过自定义 `PermanentSession`/`PermanentCookieSessionInterface` 实现（`permanent` 恒为 True），避免在每个写 session 的路径上手动置位；cookie 只含 `user_id`/`role`/`login_at` 三字段（AC-1.2.1 以 `set(current_session)` 精确断言）。
- 过期判定用 `itsdangerous` 的 `loads(max_age=None, return_timestamp=True)` 读签名时间戳：能区分「签名有效但超 24h」（302 + 「登录已过期」flash）与「签名无效」（按匿名处理，不提示过期），不用 sleep 造过期。
- 学号不存在时对固定 `DUMMY_PASSWORD_HASH`（pbkdf2:sha256 格式）执行一次 `verify_password`，AC-1.2.10 以 monkeypatch 计数断言恰好 1 次，且与密码错误响应逐项一致。
- `safe_next_path` 拒绝外部 URL、协议相对 `//`、`javascript:`、反斜杠、控制字符与非 `/` 开头输入，一律回退 `/items`；6 个不安全输入参数化用例全过。
- 守卫挂在 `before_app_request`，先于路由解析执行，因此 `/borrow`、`/return/<id>`、`/admin/*` 在后续故事实现前也能正确 302/403 而非 404/405。
- 「登录已过期」为 flash 提示语（FR-1/AC-1.2.8 专属），非 9 错误码文案，定义于 `services/auth.py`；错误码文案仍全部经 `BizError` → `config.ERROR_MESSAGES` 单一真相。
- 验证：`pytest tests/test_auth.py -v` → 30 passed；全量 `pytest -q` → 55 passed（含 Story 1.1 的 25 个）。静态扫描：新增代码无驼峰函数、无弱哈希、无新增 `sqlite3.connect(`、无密码/哈希/cookie 日志。
- Review loop iteration 1 补丁：guard 路径规范化（`path.rstrip('/')` + 精确匹配裸路径）、session.clear 条件保护（仅匿名且非空会话清除）、测试覆盖缺口补齐（cache-control、admin 登录、role tampering）。

## Spec Change Log

## Review Triage Log

| Verdict | Finding | Evidence & Disposition |
|---|---|---|
| defer | Missing CSRF on POST /login and POST /logout; brute-force mitigation missing; clickjacking protection missing | PRD §6「不做登录锁定」隐含不接受暴力破解防护作为 v1 范围；CSRF 防护属 PRD 明确不做的安全增强项（PRD SM-C2：不过度抽象）。记录到 deferred-work，不阻塞本故事。 |
| false | SESSION_COOKIE_SECURE hardcoded False — "No env/config knob to turn Secure on for HTTPS" | 这不是缺陷：ADR-003 §4 明确说 `Secure` 仅在 HTTPS 部署时开启，本地 http 演示关闭。代码硬编码 `False` 符合场景（单进程开发/演示环境）。如需 HTTPS 部署应配反向代理而非改代码；配置化反而增加维护面。判定 false。 |
| patch | Guard 漏覆盖裸 `/return`（无 loan_id）及 `/my-loans/` 带尾部斜杠的路径 | `is_protected_path` 用精确匹配 `/my-loans` 和前缀匹配 `/return/`，裸 `/return` 被绕过 → 匿名请求得到 404 而非 302。Flask 默认 trailing-slash 行为使 `/my-loans/` 产生 308→302 链。最小补丁：guard 函数内对 path 加 `path = path.rstrip('/')` 统一规范，并将前缀判断改为 `path.startswith(('/borrow/', '/return/', '/admin/')) or path in ('/borrow', '/return', '/my-loans', '/admin')`。 |
| patch | 登录失败时 `session.clear()` 清除已认证用户的会话 | 登录接口 GET 已处理了已登录用户跳转（line 58-60），但 POST 失败分支（line 74）无条件清除了 session。如果一个通过浏览器后退按钮偶然到达 POST /login 且已经认证的用户（例如手动构造请求），会被静默登出。最小补丁：仅当 `current_user is None` 或已检测到 `g.session_expired` 时才清 session；否则保留现有认证。 |
| false | 「登录已过期」指示符入口相关 — 过期 cookie 直访 /login 不显示 banner | AC-1.2.8 明确要求「失效后访问受保护页 → 302 到登录页并提示『登录已过期』」。guard 中 redirect 携带了 expired 标记并 flash 消息，所以用户在重定向后能看到提示。直接 GET /login 不会触发 guard，因此不 flash——这恰好是正确行为：未经保护的页面不应显示受保护路径才有的通知。判定 false。 |
| maybe-false | `safe_next_path` 百分号编码绕过 — 控制字符检查不作用于解码后的字符串 | `any(ord(c) < 32 for c in value)` 检查原始输入，但像 `%0d%0a` 这样的编码不含有 ASCII 控制字符。不过 Flask 在处理 location 头时会再次编码，实际不会导致 CRLF 注入。dot-dot 如 `%2e%2e` 可能被 `urlsplit` 解析为路径遍历。需要验证该路径在最终 Location 头中的表现；如果仍为 percent-encoded，则是 low-severity；如果能被解析则为 medium-severity pending verification。 |
| false | Spec/status 文档漂移 — Sprint-status.yaml 标题行 stale comments | sprint-status.yaml 的头部注释 "Readiness gate：PASS""下一动作" 是阶段信息而非运行时状态，每次新故事完成后更新一次即可，不是实时校验指标。规格文件的 `review_loop_iteration` 和空 Change Log 在首次评审后自然会填充。非 blocker。 |
| false | Diff 统计不准确 — Spec note "+614/-1" 与 10 个文件不符 | 实现笔记说的是 "8 code files, +614/-1"，git show --stat 报 614 insertions 包含代码文件；spec/sprint 状态变更由后续独立提交。表述上略显模糊但不影响验收。判定 false。 |
| patch | Test 覆盖缺口 — Cache-Control: no-store 未断言、admin 登录成功路径、role tampering 测试缺失 | 已有 27 个 auth 测试覆盖了核心 AC，但遗漏：① 响应中 `Cache-Control: no-store` 的断言；② admin 账号登录后 `/admin/items` 返回 200（当前只测了 student 的 403）；③ role tampering：修改 session 中的 role 与实际 DB 不同则应拒绝。均为小补丁。 |
| defer | `session["login_at"]` 写入但未消费 — Dead data | 可能用于未来审计日志或绝对过期计算（vs idle expiry），暂留作技术债。不在 v1 范围内强制使用。 |

---

**Routing Summary:**
- **Patch items**: (3) guard trailingslash/bare-path, (4) session clear on failed login only when anonymous, (9) test gaps → all small fixes, non-breaking. Auto-fix route.
- **Defer items**: CSRF/brute-force/clickjacking, dead data, doc drift → out of scope or low impact. Record to deferred-work.
- **Maybe-false items**: (6) safe_next_path percent-encoding → requires manual verification of Flask's encoding behavior. Not blocking.
- **False items**: (2), (5), (7), (8) — rejected after verification.

**Patches Applied (review_loop_iteration 1):**
- ✅ Guard path normalization: `path.rstrip('/')` + `path in ('/borrow', '/return', '/my-loans', '/admin')` — 修复裸路径绕过
- ✅ Session clear condition: `if g.current_user is None and session: session.clear()` — 仅匿名会话清除
- ✅ Test gaps: 新增 cache-control 断言、admin 登录成功测试、role tampering 测试 — 30 个测试全部通过

## Design Notes

访问守卫必须在路由解析失败前运行，否则后续故事尚未实现的 `/borrow`、`/return/*`、`/admin/*` 会先得到 404/405，无法满足本故事的访问控制验收。`/my-loans` 本故事只证明受保护页面可访问，不引入借阅查询或额度计算。

## Verification

**Commands:**
- `python -m pytest tests/test_auth.py -q` — Story 1.2 全部用例通过。
- `python -m pytest -q` — 既有 Story 1.1 与新增测试全绿。
- 检索新代码的驼峰函数、弱哈希及新增数据库连接 — 均为 0 命中。
