---
title: 'Story 3.1：管理员新增物品与管理列表'
type: 'feature'
created: '2026-11-10'
status: 'done'
baseline_commit: 'cc31e7a'
---

# Story 3.1：管理员新增物品与管理列表

## 目标与口径
- 管理员在 `/admin/items` 新增物品（名称 + 类别），并在同一页面看到**全部**清单（含停用项与在借人）。
- 用户三条硬约束：① D-012 权限边界——`role` 判定只允许蓝图级统一拦截，业务代码零 role 分支；② FR-6 校验——名称 strip 后 1–50、类别枚举、允许重名，失败统一 400 `INVALID_INPUT`；③ 只增不删改——编辑/删除/停用/恢复均不在本故事（改名会破坏借阅历史的名称一致性，v1 依 D-007 砍了快照字段，人类裁决定死）。

## 实现
- **守卫改造（本次最大结构变更）**：403 授权判定从 `routes/auth.py` 全站守卫迁出。
  - `routes/auth.py::guard_protected_paths` 瘦身为纯认证拦截（只管 302 → `/login?next=`，不含任何 role 分支；保留 `/admin` 前缀使未登录访问任意 admin 路径都先撞 302，认证先于路由解析，AC-1.2.5 语义不回退）。
  - 新增 `routes/admin.py`：`Blueprint("admin", url_prefix="/admin")` + `@bp.before_request` 蓝图级守卫——**全库唯一** `role != "admin"` 判定点（可 grep 验证）。守卫与路由同前缀物理绑定，Story 3.2~3.4 的删除/停用/恢复路由挂进本蓝图即自动被覆盖，不存在漏挂路径。
- `services/admin.py::create_item(raw_name, category)`：strip → 1–50（长度真相 = `config.MAX_NAME_LEN`）→ 类别严格枚举 `("book","equipment")`（大小写变体拒绝）→ 失败 `BizError(400,"INVALID_INPUT")`；写入 `status` 恒 `'available'` 字面量（AR-4），`INSERT` 包在 `write_transaction()`（BEGIN IMMEDIATE，PC-4）；名称不做唯一校验（ADR-006 一物一行）。
- `services/items.py::list_items_with_state(query=None, include_unavailable=False)`：新增参数供管理列表复用**同一**派生查询（AR-5/AC-3.4.6 前置），学生端默认行为逐字不变。
- `templates/admin_items.html`：SSR 表单 `form method=post`（无 fetch/XHR/JSON，AC-3.1.8）+ 全量列表（已停用→「已停用」、在借→标注在借人姓名）；`maxlength` 引用注入的 `max_name_len`（模板不写死数字，沿用 AC-2.5.9 口径）。
- `app.py`：注册 admin 蓝图；context processor 追加 `MAX_NAME_LEN`。
- `routes/auth.py` 的 POST 登录失败分支仍需 `BizError` 导入（首跑 NameError 即误删该 import，已复原）。

## 已交付行为
- 管理员新增「热熔胶枪 #3」→ 302 + flash「已添加」→ 学生端 `GET /items?q=胶枪` 立即可搜到（AC-3.1.3）。
- 空名/纯空格/51 字/缺字段 → 400 `INVALID_INPUT` 零写入；恰好 50 字接受（边界）；strip 后入库（AC-3.1.4）。
- 类别空值/`furniture`/`Book` → 400 零写入（AC-3.1.5）。
- 同名两条记录独立 id 共存（AC-3.1.6）。
- 管理列表含停用项（标「已停用」）与在借人姓名；对照学生端不显示停用项（AC-3.1.7）。
- 学生/未登录访问 GET+POST `/admin/items`：403/302，`items` 快照逐字段不变（AC-3.1.1/3.1.2）。
- 未注册的 `/admin/*/edit|delete|unavailable|available`、`PUT`、尾斜杠路径对学生一律 404（认证后路由不存在），无任何编辑/删除入口泄漏进 3.1。

## 测试
- `tests/test_admin.py`：18 例——AC-3.1.1~3.1.8 逐条 + D-012 结构守卫 2 例（全库 `[... "role"] !=/== "admin"` 命中恰为 `{admin.py: 1}`；403 必须位于 `@bp.before_request` 段且视图体内无 role）+ 只增不删改端点扫描 + 守卫改造回归哨兵。
- 结构自检（grep 判据）：`UPDATE items` 0 命中；`BEGIN DEFERRED` 0；`sqlite3.connect(` 仍仅 db.py 一处；额度聚合仍仅一处；模板无 fetch/XHR。
- 全量回归：**141 passed**（123 → 141：本故事 18 例，零回归；Story 1.2 的 AC-1.2.5/1.2.7 admin 用例在守卫迁移后原样通过）。

## Follow-ups
- CSRF 延期口径沿用（deferred-work，PRD §6 明确不做）。
- 「已添加」flash 文案为 AC-3.1.3 原文；400 响应复用 `error.html` 统一渲染（`INVALID_INPUT` + 中文文案同源 `config.ERROR_MESSAGES`）。
- 管理列表的停用标注在 Story 3.3 上线停用动作前仅可由直接 SQL 构造验证（同 Story 2.2 技术要点的授权口径）。
