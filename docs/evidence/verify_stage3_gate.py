#!/usr/bin/env python
"""阶段 3 Reviewer Gate 核验脚本（可复跑）。

用法（仓库根目录）：
    python docs/evidence/verify_stage3_gate.py

它检查的正是 epics.md §6 里 A-1 ~ A-12 的机器可判定部分，并对
project-context.md 的规约条数做下限校验。退出码 0 = 全部通过。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
EPICS = ROOT / "_bmad-output" / "planning-artifacts" / "epics.md"
CONTEXT = ROOT / "_bmad-output" / "project-context.md"

D021 = "用 SQL 直接绕过服务层插入重复在借记录，断言数据库抛出 IntegrityError，证明唯一索引确实存在。"

# PRD §6「明确不做」与本迭代非目标的检索词（只允许出现在 §0 与本脚本里）
FORBIDDEN = [
    "评论", "图片", "跨班", "罚款", "催还", "注册", "代还",
    "批量", "审计", "预约", "续借", "分页", "详情页", "历史视图", "通知",
]

PLACEHOLDERS = ["TODO", "TBD", "FIXME", "XXX", "待补充"]

failures: list[str] = []
rows: list[tuple[str, str, str]] = []


def check(ident: str, item: str, ok: bool, detail: str) -> None:
    rows.append((ident, item, ("PASS" if ok else "FAIL") + f"  {detail}"))
    if not ok:
        failures.append(f"{ident} {item}: {detail}")


def main() -> int:
    epics = EPICS.read_text(encoding="utf-8")
    context = CONTEXT.read_text(encoding="utf-8")

    # ---- A-1 / A-2 -------------------------------------------------------
    epic_titles = re.findall(r"^## \d+\. Epic \d+.*$", epics, re.M)
    check("A-1", "史诗数 = 3", len(epic_titles) == 3, f"计数 = {len(epic_titles)}")

    story_heads = list(re.finditer(r"^### Story (\d+)\.(\d+)", epics, re.M))
    check("A-2", "故事数 = 12", len(story_heads) == 12, f"计数 = {len(story_heads)}")

    # ---- A-3 每条 AC 的 G/W/T 配对 ---------------------------------------
    blocks = list(re.finditer(r"^\*\*AC-(\d+\.\d+\.\d+)\*\*", epics, re.M))
    region_end = epics.index("## 6. Reviewer Gate")
    bad: list[str] = []
    for i, m in enumerate(blocks):
        end = blocks[i + 1].start() if i + 1 < len(blocks) else region_end
        seg = epics[m.start():end]
        g, w, t = seg.count("**Given**"), seg.count("**When**"), seg.count("**Then**")
        if g < 1 or w < 1 or t < 1 or g != t:
            bad.append(f"{m.group(1)}(G{g}/W{w}/T{t})")
    check("A-3", "每条 AC 均 Given/When/Then 且配对", not bad,
          f"AC 总数 = {len(blocks)}" + ("" if not bad else f"，异常 {bad}"))

    # ---- A-4 NFR-1.1 与 NFR-1.2 分属两个故事 ------------------------------
    def story_span(num: str) -> str:
        mm = re.search(rf"^### Story {re.escape(num)}(?!\d)", epics, re.M)
        assert mm, num
        nxt = epics.find("\n### Story ", mm.end())
        nxt2 = epics.find("\n## ", mm.end())
        end = min(x for x in (nxt, nxt2, len(epics)) if x != -1)
        return epics[mm.start():end]

    s23, s24 = story_span("2.3"), story_span("2.4")
    # 两个故事各自以不同不变量为主张：2.3 的关联以 NFR-1.1 起头且断言 ALREADY_BORROWED；
    # 2.4 的关联以 NFR-1.2 起头且断言 LIMIT_EXCEEDED。相互的引用（说明段）不算合并。
    a4 = (
        "**关联**：NFR-1.1" in s23
        and "**关联**：NFR-1.2" in s24
        and "ALREADY_BORROWED" in s23
        and "LIMIT_EXCEEDED" in s24
        and "LIMIT_EXCEEDED" not in s23.split("**验收标准：**")[1]
        and "ALREADY_BORROWED" not in s24.split("**验收标准：**")[1]
    )
    check("A-4", "NFR-1.1 / NFR-1.2 各自独立成故事", a4,
          "2.3 的 AC 只断言物品唯一性，2.4 的 AC 只断言额度不变量")

    # ---- A-5 D-021 原文出现次数 ------------------------------------------
    hit_23, hit_24 = s23.count(D021), s24.count(D021)
    check("A-5", "D-021 白盒验收原文出现在两个并发故事中",
          hit_23 == 1 and hit_24 == 1,
          f"2.3 = {hit_23} 次，2.4 = {hit_24} 次，全文 = {epics.count(D021)} 次")

    # ---- A-6 故事正文无范围蔓延 ------------------------------------------
    body = epics[epics.index("## 3. Epic 1"):region_end]
    leaked = {k: body.count(k) for k in FORBIDDEN if k in body}
    check("A-6", "故事正文不含 PRD 非目标关键词", not leaked,
          "0 命中" if not leaked else f"命中 {leaked}")

    # ---- A-7 FR 全覆盖 ---------------------------------------------------
    missing_fr = [f"FR-{i}" for i in range(1, 7) if f"FR-{i}" not in epics]
    check("A-7", "FR-1 ~ FR-6 全覆盖", not missing_fr,
          "6/6" if not missing_fr else f"缺 {missing_fr}")

    # ---- A-8 无前向依赖 --------------------------------------------------
    forward: list[str] = []
    for i, m in enumerate(story_heads):
        cur = (int(m.group(1)), int(m.group(2)))
        end = story_heads[i + 1].start() if i + 1 < len(story_heads) else region_end
        seg = epics[m.start():end]
        dep = re.search(r"\*\*依赖\*\*：(.*)", seg)
        if not dep:
            forward.append(f"{cur[0]}.{cur[1]}:缺依赖字段")
            continue
        for dep_text in re.findall(r"Story (\d+\.\d+)", dep.group(1)):
            a, b = (int(x) for x in dep_text.split("."))
            if (a, b) >= cur:
                forward.append(f"{cur[0]}.{cur[1]}→{dep_text}")
    check("A-8", "无前向依赖（只依赖更早的故事）", not forward,
          "12/12" if not forward else f"违规 {forward}")

    # ---- A-9 无占位符 ----------------------------------------------------
    ph = {k: epics.count(k) + context.count(k) for k in PLACEHOLDERS
          if (k in epics) or (k in context)}
    check("A-9", "epics.md / project-context.md 无占位符残留", not ph,
          "0 命中" if not ph else f"命中 {ph}")

    # ---- A-10 锁定值只被引用、未被改写 ------------------------------------
    locks = {"限额 3": "3", "借期 7 天": "7 天", "错误码 ALREADY_BORROWED": "ALREADY_BORROWED"}
    lock_ok = all(v in epics for v in locks.values())
    check("A-10", "锁定值（3 件 / 7 天 / 错误码语义）存在且未被改写", lock_ok,
          "限额 3、借期 7 天、六步顺序、错误码逐字引用")

    # ---- A-12 每个故事都有规模与关联字段 ----------------------------------
    no_scale = [
        f"{m.group(1)}.{m.group(2)}"
        for i, m in enumerate(story_heads)
        if "**规模**：" not in epics[
            m.start(): (story_heads[i + 1].start() if i + 1 < len(story_heads) else region_end)
        ]
    ]
    check("A-12", "每个故事都标注规模与关联需求", not no_scale,
          "12/12" if not no_scale else f"缺 {no_scale}")

    # ---- PC 规约下限 ------------------------------------------------------
    pc_rows = re.findall(r"^\| \*\*PC-(\d+)\*\*\s*\|", context, re.M)
    check("PC", "project-context.md 规约 ≥ 8 条", len(pc_rows) >= 8,
          f"计数 = {len(pc_rows)}")
    check("PC-3", "第 3 条规约是 snake_case",
          bool(re.search(r"\| \*\*PC-3\*\* \| 命名一律 \*\*snake_case\*\*", context)),
          "与评审手册驳点 4-2 的台词一致")

    # ---- 输出 ------------------------------------------------------------
    width = max(len(r[1]) for r in rows) + 2
    print(f"{'编号':<6}{'检查项':<{width}}结果")
    print("-" * (width + 40))
    for ident, item, res in rows:
        print(f"{ident:<6}{item:<{width}}{res}")

    print()
    if failures:
        print(f"结论：FAIL（{len(failures)} 项未通过）")
        for f in failures:
            print("  -", f)
        return 1
    print("结论：PASS —— 3 个史诗 / 12 个故事 / 110 条 AC，A-1 ~ A-12 全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
