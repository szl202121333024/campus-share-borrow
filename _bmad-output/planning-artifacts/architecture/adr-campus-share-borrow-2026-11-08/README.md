---
title: 架构决策索引（阶段 2 产物）
status: final
created: 2026-11-08
updated: 2026-11-08
phase: 2 / bmad-architecture
---

# 架构决策索引 · campus-share-borrow

- **上游**：[PRD](../../prds/prd-campus-share-borrow-2026-11-08/prd.md)（`status: final`）、[decision-log.md](../../../../decision-log.md)（D-001 ~ D-021）
- **本阶段产物**：ADR-001 ~ ADR-007，每条四段齐全（背景 / 决定 / 否决的备选方案 / 后果）
- **下游**：阶段 3 `bmad-create-epics-and-stories`（产出 3 史诗 + ≥12 故事 + `project-context.md`）

## 1. ADR 一览

| ADR | 主题 | 决定（一句话） | 否决备选 | 来源 |
|---|---|---|---|---|
| [ADR-001](ADR-001-rendering.md) | 渲染方式与服务边界 | Flask + Jinja2 服务端渲染，单进程单端口，**无独立 API 层**，写操作 POST + 302 | 3 条 | D-017 |
| [ADR-002](ADR-002-concurrency-uniqueness.md) | 并发唯一性 | `item_id` 上的**部分唯一索引**（`WHERE returned_at IS NULL`）兜底物品超卖 + `BEGIN IMMEDIATE` 保证额度原子 + 捕获 `IntegrityError` → 409 | 5 条 | D-009、D-018、D-020、D-021 |
| [ADR-003](ADR-003-session.md) | 会话方案 | Flask 签名 cookie session（无状态）；**明确接受**「服务端无法主动吊销」风险 | 5 条 | D-019 |
| [ADR-004](ADR-004-password-storage.md) | 密码存储 | PBKDF2-SHA256，**显式** `method="pbkdf2:sha256"`（默认值已变为 scrypt） | 5 条 | 规范确认 |
| [ADR-005](ADR-005-concurrency-deployment.md) | 并发与部署 | WAL + `busy_timeout=5000` + `foreign_keys=ON`，单进程 `python app.py` | 5 条 | 规范确认 |
| [ADR-006](ADR-006-item-model.md) | 物品模型 | **一物一行**单件实体，无任何数量/库存列；同款多件录多条 | 5 条 | D-001 |
| [ADR-007](ADR-007-item-state-machine.md) | 物品状态机 | 「存储态 + 派生态」混合：`items.status` 只存 `available`/`unavailable`，`borrowed` 由 `loans` 派生，唯一写入者是管理员 | 5 条 | D-014、D-015 |

**合计**：7 条 ADR，33 个「否决的备选方案」，每个备选都带独立的否决理由。

## 2. Reviewer Gate 自检结果（2026-11-08）

| 检查项 | 判定方式 | 结果 |
|---|---|---|
| 7 条 ADR 齐全 | 目录内 `ADR-001` ~ `ADR-007` | ✅ 7/7 |
| 每条四段完整 | `## 1. 背景` / `## 2. 决定` / `## 3. 否决的备选方案` / `## 4. 后果` | ✅ 7/7 |
| 否决备选均含理由 | 「否决理由」段落数 vs 备选数 | ✅ 33/33 |
| 无占位符残留 | 检索 `TODO`/`TBD`/`FIXME`/`XXX`/「待补充」 | ✅ 0（3 处为「策略」一词的误匹配） |
| 状态均为 `accepted` | frontmatter `status` | ✅ 7/7 |
| PRD 产品值已对齐 | 限额 3 件、借期 7 天、判定顺序六步、9 个错误码 | ✅ 一致（O-1 已按 D-023 订正） |
| 每条 ADR 指向 decision-log | frontmatter `decision_log` | ✅ 5 条有编号，2 条标注为「无争议确认」并说明理由 |

**发现的 PRD 实现层问题（已提出，未私自修改 PRD）**：

1. **FR-1「登出后旧 cookie 失效」在无状态 session 下无法真正实现** → 人类裁决接受风险，写入 ADR-003 §4，并要求同步 `README` 与 `retrospective.md`（D-019）。
2. **`generate_password_hash` 默认算法已非 PBKDF2** → 转为实现约束「必须显式传 `method`」+ 一条哈希前缀断言测试（ADR-004 §5）。
3. **评审手册初稿的唯一索引措辞错误**（`UNIQUE(user_id, item_id)`）→ 已修正 playbook 并加注（D-018）。

## 3. 对阶段 3 的硬约束（写故事与 `project-context.md` 时必须体现）

1. **借阅写路径整体包在 `BEGIN IMMEDIATE` 内**：先校验（⑥ 步固定顺序）→ 再 `INSERT` → 捕获 `IntegrityError` 映射 409。禁止 `BEGIN DEFERRED`、禁止「先查后写」当唯一裁决（ADR-002）。
2. **唯一索引的存在性必须被直测**：除黑盒并发测试外，必须有「绕过服务层直接 `INSERT`，断言抛 `IntegrityError`」的测试 —— **因为 ④ 已在其前面拦截，正常路径下索引几乎不可达**（D-021，本阶段最重要的一条）。
3. **归还只能写 `loans`**：`UPDATE loans SET returned_at=? WHERE id=? AND user_id=? AND returned_at IS NULL`，用 `rowcount` 判成败（NFR-1.3）。代码评审 `grep "UPDATE items"` 应仅命中管理员停用/恢复上架两处（D-014）。
4. **NFR-1.1 与 NFR-1.2 必须是两个独立故事**，不得合并：前者考唯一索引，后者考 `BEGIN IMMEDIATE`（PRD NFR-1.2 明确要求）。
5. **物品状态永不存 `borrowed`**：`CHECK` 约束兜底；列表状态由单一派生函数产出，禁止第二份 SQL（ADR-007、D-013 同源）。
6. **额度只能有一处真相**：`get_remaining_quota(student_id)` 单条聚合查询，前置校验与页面指示共用（D-013）。
7. **无前端构建链**：仓库不得出现 `package.json` / `vite.config.*` / `node_modules` / `dist`（ADR-001，可直接检出）。
8. **依赖下限**：`Flask>=3.1.0` + `Werkzeug>=3.1.0`（Python 3.14 兼容硬性要求，ADR-005 §5.1）。
9. **启动自举必须断言 `PRAGMA journal_mode` 返回 `wal`**，否则静默退化（ADR-005 §5.2）。
10. **所有角色统一业务规则**：无 `if role != 'admin'` 的限额分支（D-012）。

## 4. ADR 之间的依赖关系

```
ADR-006 物品模型（一行=一件）
   └─> ADR-002 部分唯一索引 ON loans(item_id)   ← 依赖「一行=一件」才等价于「一件只归一人」
ADR-007 状态机（borrowed 派生）
   └─> ADR-002 schema 的 CHECK(status IN (available,unavailable))  ← 物理层禁止借态入库
   └─> ADR-005 单进程 + WAL（派生查询与写事务共存）
ADR-001 SSR
   └─> ADR-003 同源 cookie session    ← 分离则必须改 token
   └─> ADR-005 单进程一条命令          ← 无构建产物才能一条命令
ADR-004 密码哈希（独立）
```

*文档结束。阶段 2 锁定。下一步：开新对话执行 `bmad-create-epics-and-stories`。*
