# AGENTS.md · 仓库级工作约定

> 本文件给**每一个**进入本仓库的 AI 会话（含 BMAD 各工作流）读取。规则优先于个人习惯。

## 1. 提交纪律（硬性）

- **每一次修改文档或代码后，立刻 `git commit`。** 不允许把多个不相关的改动攒成一大笔，也不允许「先干完再说」。
- 提交粒度：一个逻辑变更 = 一笔提交。文档类用 `docs: ...`，代码类用 `feat: ...` / `fix: ...` / `test: ...`。
- **提交前必须确认工作树状态**：`git status --short` 应只包含本次要提交的文件。
- 课程作业目标是 **20+ 笔小而清晰的提交**——刻意保持小步提交，不要合并历史。

### 1.1 推送纪律（硬性）

- **每笔 `commit` 之后立即 `git push origin main`**，保持远端与本地同步。
- **push 失败必须立刻停下并报告人类**（附完整报错），不得继续累积本地提交当作已完成——「远端没记录」等于留痕不存在。
- 已知失败模式：本机 `credential.helper=manager`，但 GitHub 条目曾出现 `schannel: SEC_E_NO_CREDENTIALS`，即凭据失效。修复方式（由人类手动执行一次，之后凭证会缓存）：
  ```powershell
  cmdkey /delete:git:https://github.com   # 清掉失效条目
  git push origin main                    # 弹窗重新登录 GitHub
  ```
- 判定同步状态：`git status -sb` 显示 `ahead N` 即为存在未推送提交，必须处理。

## 2. 本机 git 不在 PATH

每次使用 git 前先执行：

```powershell
$env:Path = "D:\Program Files\Git\cmd;" + $env:Path
```

## 3. 工作流隔离

- 一个工作流 = 一个**新对话**。阶段切换时必须明确提示「请开新对话」。
- 严禁同一对话里既写 PRD 又写代码；严禁在同一对话里跨阶段作业。

## 4. 不得擅改的锁定值

以下产品值在阶段 1 已锁定（`prd.md` `status: final`），**任何下游文档不得改写**，需要变更必须先提出来由人类裁决：

- 借阅限额 **3 件**；借期 **7 天**；
- 借阅错误**判定顺序六步**：① 未登录 302 → ② 不存在 404 → ③ 停用 409 → ④ 本人已持有 409 → ⑤ 限额 409 → ⑥ 唯一约束兜底 409；
- 9 个错误码的语义（`RESOURCE_NOT_FOUND` 与 `INVALID_CREDENTIALS` 是刻意的两处合并）。

## 5. 留痕规则

- 任何**人类否决或实质修改 AI 方案**的动作，必须记入 `decision-log.md`（格式：触发 / 智能体建议 / 人类判断依据 / 结果 / 事后验证）。
- 「事后验证」列不得留空；尚未验证的写「（未验证）」并在后续阶段回填。
- 下一个可用编号：**D-027**。

## 6. 语言与格式

- 产物文档用**中文**；代码标识符与小标题可用英文。
- 文档不得留 `TODO` / `TBD` / 占位符；未确认的技术假设标 `[ASSUMPTION]` 或 `[待验证]`，核实后转正为 `[已验证]` 并附来源。

## 7. 关键路径

| 类别 | 路径 |
|---|---|
| 需求基线 | `_bmad-output/planning-artifacts/prds/prd-campus-share-borrow-2026-11-08/prd.md` |
| 架构决策 | `_bmad-output/planning-artifacts/architecture/adr-campus-share-borrow-2026-11-08/`（ADR-001~008 + README 索引；ADR-008 为阶段 4 实施中依 D-024 裁决追加） |
| 史诗与故事 | `_bmad-output/planning-artifacts/epics.md`（3 史诗 / 12 故事 / 110 条 AC，**故事数量上限由 D-022 锁定，不得新增**） |
| 实现规约 | `_bmad-output/project-context.md`（PC-1 ~ PC-15，写代码前先读、写完按 §4 自检） |
| 决策日志 | `decision-log.md` |
| 评审手册 | `docs/review-playbook.md` |
| 作业要求 | `docs/assignment-brief.md` |
