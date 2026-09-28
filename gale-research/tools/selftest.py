#!/usr/bin/env python3
"""selftest.py —— check_gale_report.py 的回归测试（切片 1）

用法:
    python selftest.py

退出码: 0 全过（含显式 SKIP）/ 1 有 FAIL

🔴 纪律（与 handoff-dou/tools/selftest.py 同源）：
  **未测试的判据 = 没有判据。不可重跑的验证 = 一次性证据。**
  **断言不依赖环境现状** —— 每个用例自建临时目录 + 自带合成 SKILL.md，
  绝不读真仓（真仓的档位表变了不该让本测试变红；反之也不该让它变绿）。

每个检查都必须有至少一个「把它改坏就变红」的用例；用例注释里写明这一条。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
# GALE_CHECK 允许指向一份被故意改坏的副本 —— 变异测试用（见 plan §Phase 3 验收 2）
SCRIPT = Path(os.environ.get("GALE_CHECK") or (HERE / "check_gale_report.py"))

GOOD_SKILL = """# fake skill
### 量级契约表
| 档 | 轮次构成 | R1 并行 | R2 深挖上限 | 预算封顶(搜索/抓取) |
|---|---|---|---|---|
| L1 速览 | 仅 R1 | 3~4 路 | — | ~8 / 0 |
| L2 标准 | R1→R2 | 4~8 路 | 6~8 | ~15 / 10 |
| L3 深度 | R1→R2→R3 | 4~8 路 | 6~8 | ~22 / 15 |
| L4 扩展 | R1→R2→R3→R4 | 6~10 路 | 10~12 | ~30 / 20 |
"""

# 无波浪号的变体 —— 解析器必须**两种都接受**（格式漂移可见但不算坏）
NOSQUIGGLE_SKILL = GOOD_SKILL.replace("~30 / 20", "30/20").replace("~8 / 0", "8/0")

BROKEN_SKILL = """# fake skill
| 档 | 轮次构成 | R1 并行 | R2 深挖上限 | 预算封顶(搜索/抓取) |
|---|---|---|---|---|
| L4 扩展 | R1→R2→R3→R4 | 6~10 路 | 10~12 | 三十/二十 |
"""

GAPS_CLOSED = """## 5. 缺口裁决表
| 缺口 | 产生于 | 闭合所需证据 | 状态 | 证据 |
|---|---|---|---|---|
| G1 定价页不含该档 | R3 | 定价页原文 | 已闭合 | https://a.example/pricing |
| G2 二次开发接口 | R3 | schema 原文 | 已闭合 | https://a.example/api |
"""

GAPS_ACTIONABLE = """## 5. 缺口裁决表
| 缺口 | 产生于 | 闭合所需证据 | 状态 | 证据 |
|---|---|---|---|---|
| G1 定价页不含该档 | R3 | 定价页原文 | 未闭合·可动作 | 下一步:搜 "vendor pricing tier" |
| G2 批量授权价目 | R3 | 定价页/合同范本 | 未闭合·可动作 | 下一步:抓 vendor 企业版定价页 |
"""

# 别名节名（骨架曾把 §5 限 L3/L4 → L1/L2 作者自造节名；2026-09-25 pilot 实测）
GAPS_ACTIONABLE_ALIAS = GAPS_ACTIONABLE.replace("## 5. 缺口裁决表", "## 5. 缺口清单")

GAPS_INACTIVE = """## 5. 缺口裁决表
| 缺口 | 产生于 | 闭合所需证据 | 状态 | 证据 |
|---|---|---|---|---|
| G1 批量授权价 | R3 | 商务条款 | 未闭合·不可动作 | 不可动作:需商务洽谈 |
"""


def report(
    tier: str = "L4",
    b: str = "1",
    used_s: int = 11,
    cap_s: int = 30,
    used_f: int = 18,
    cap_f: int = 20,
    rounds: str = "R1 搜索 6/抓取 0 · R2 搜索 3/抓取 12 · R3 搜索 1/抓取 4 · R4 搜索 1/抓取 2",
    stop: str = "SUFFICIENT",
    gaps: str = GAPS_CLOSED,
    extra_meta: str = "",
    omit_stop_in_meta: bool = False,
    mention_stop_in_prose: bool = False,
) -> str:
    meta = f"> 日期 · 方法(档位 {tier} · 实际止于 R4"
    if not omit_stop_in_meta:
        meta += f" · 停止原因: STOP={stop}"
    meta += ") · 场景一句话"
    ledger = f"> 用量台账: 搜索 {used_s}/{cap_s} · 抓取 {used_f}/{cap_f} (生效上限 = 档位基准 ×B{b}) · 逐轮: {rounds}"
    prose = ""
    if mention_stop_in_prose:
        prose = "\n本节讨论 停止原因: STOP= 这个字段该怎么填，以及为什么。\n"
    return (
        "# 测试调研报告\n"
        + meta + "\n"
        + ledger + "\n"
        + extra_meta
        + prose
        + "\n1. 术语对照表\n2. 候选对比总表\n3. 排除清单\n4. 关键技术判断\n"
        + gaps
        + "6. 推荐结论\n7. 来源列表\n"
    )


def run(files: dict[str, str], args: list[str]) -> tuple[int, str]:
    """在临时目录里放 files，跑校验器。files 的 key 是相对路径。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for name, body in files.items():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
        cmd = [sys.executable, str(SCRIPT)] + [a.replace("{TMP}", str(root)) for a in args]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")


RESULTS: list[tuple[str, str, str]] = []


def case(name: str, ok: bool, note: str = "") -> None:
    RESULTS.append((name, "PASS" if ok else "FAIL", note))


def main() -> int:
    SK = "{TMP}/SKILL.md"

    # ---- 1. 合规报告必须过（证明判据不是恒红）----
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": report()}, ["--skill", SK, "{TMP}/r.md"])
    case("good_l4_sufficient", c == 0, f"exit={c}")

    # ---- 2. BUDGET_EXHAUSTED 带齐 N 与 ×M 也必须过 ----
    body = report(stop="BUDGET_EXHAUSTED", gaps=GAPS_ACTIONABLE,
                  extra_meta="> ⚠️ 可动作缺口 2 条 · 建议倍率 ×3(同档位重跑)\n")
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("good_l4_budget", c == 0, f"exit={c} {o.strip()[:80]}")

    # ---- 3. SUFFICIENT 却有可动作缺口 → 检查 3 必须红 ----
    body = report(stop="SUFFICIENT", gaps=GAPS_ACTIONABLE)
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("block_sufficient_with_open_gaps", c == 1 and "检查3" in o, f"exit={c}")

    # ---- 3b. 反向：不可动作缺口 + SUFFICIENT → **不该**报（解死锁的判据）----
    body = report(stop="SUFFICIENT", gaps=GAPS_INACTIVE)
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("pass_sufficient_with_inactive_gap", c == 0, f"exit={c} {o.strip()[:80]}")

    # ---- 4. BUDGET_EXHAUSTED 缺 ×M → 检查 2 ----
    body = report(stop="BUDGET_EXHAUSTED", gaps=GAPS_ACTIONABLE,
                  extra_meta="> ⚠️ 可动作缺口 3 条\n")
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("block_budget_no_multiplier", c == 1 and "检查2" in o, f"exit={c}")

    # ---- 4b. BUDGET_EXHAUSTED 但 N=0 → 检查 2 ----
    body = report(stop="BUDGET_EXHAUSTED", gaps=GAPS_ACTIONABLE,
                  extra_meta="> ⚠️ 可动作缺口 0 条 · 建议倍率 ×3\n")
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("block_budget_gap_n_zero", c == 1 and "检查2" in o, f"exit={c}")

    # ---- 4c/4d/4e. TIER_LIMIT（预算未触顶但本档结构到顶）----
    # L2 无 R3，收束时仍有可动作缺口 → 补救是「升档」而非「加预算」
    L2_LEDGER = dict(tier="L2", used_s=9, cap_s=15, used_f=8, cap_f=10,
                     rounds="R1 搜索 6/抓取 0 · R2 搜索 3/抓取 8")
    body = report(**L2_LEDGER, stop="TIER_LIMIT", gaps=GAPS_ACTIONABLE,
                  extra_meta="> ⚠️ 可动作缺口 2 条 · 建议升档 L3\n")
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("good_l2_tier_limit", c == 0, f"exit={c} {o.strip()[:90]}")

    body = report(**L2_LEDGER, stop="TIER_LIMIT", gaps=GAPS_ACTIONABLE,
                  extra_meta="> ⚠️ 可动作缺口 2 条\n")
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("block_tier_limit_no_upgrade", c == 1 and "检查2" in o and "升档" in o, f"exit={c}")

    body = report(**L2_LEDGER, stop="TIER_LIMIT", gaps=GAPS_ACTIONABLE,
                  extra_meta="> ⚠️ 建议升档 L3\n")
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("block_tier_limit_no_gap_n", c == 1 and "检查2" in o, f"exit={c}")

    # ---- 5. 超顶却报 SUFFICIENT → 检查 6 ----
    body = report(used_s=40, cap_s=30, stop="SUFFICIENT")
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("block_overcap_sufficient", c == 1 and "检查6" in o, f"exit={c}")

    # ---- 5b. 超顶但报 NO_PROGRESS → 检查 6 不该报（只判 SUFFICIENT）----
    body = report(used_s=40, cap_s=30, stop="NO_PROGRESS",
                  rounds="R1 搜索 20/抓取 0 · R2 搜索 15/抓取 12 · R3 搜索 3/抓取 4 · R4 搜索 2/抓取 2",
                  extra_meta="> ⚠️ 可动作缺口 2 条 · 建议倍率 ×3\n")
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("pass_overcap_not_sufficient", c == 0, f"exit={c} {o.strip()[:80]}")

    # ---- 6/7. 算术：搜索维、抓取维各一个用例（只坏一边必须能抓到）----
    body = report(used_s=12)  # Σs = 11 ≠ 12
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("block_ledger_arithmetic_s", c == 1 and "检查5" in o and "搜索维" in o, f"exit={c}")

    body = report(used_f=19)  # Σf = 18 ≠ 19
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("block_ledger_arithmetic_f", c == 1 and "检查5" in o and "抓取维" in o, f"exit={c}")

    # ---- 8. 生效上限 ≠ base × B → 检查 4 ----
    body = report(b="1.5", cap_s=30, cap_f=20)  # 应为 45/30
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("block_ledger_cap_mismatch", c == 1 and "检查4" in o, f"exit={c}")

    # ---- 9. 缺 ×B → 检查 4（堵 fail-open：B 不显式写就无法判定口径）----
    body = report().replace(" (生效上限 = 档位基准 ×B1)", "")
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("block_ledger_no_B", c == 1 and "检查4" in o, f"exit={c}")

    # ---- 10. 未知档位 → 检查 4 ----
    body = report(tier="L9", cap_s=30, cap_f=20)
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("block_unknown_tier", c == 1 and "检查4" in o, f"exit={c}")

    # ---- 11. 无波浪号的档位表必须同样解析成功 ----
    c, o = run({"SKILL.md": NOSQUIGGLE_SKILL, "r.md": report()}, ["--skill", SK, "{TMP}/r.md"])
    case("pass_tier_table_no_squiggle", c == 0, f"exit={c} {o.strip()[:80]}")

    # ---- 12. 档位表损坏 → exit 2（fail-closed，不静默跳过）----
    c, o = run({"SKILL.md": BROKEN_SKILL, "r.md": report()}, ["--skill", SK, "{TMP}/r.md"])
    case("exit2_malformed_tier_table", c == 2, f"exit={c}")

    # ---- 13. 反真空：停止原因只在正文提到、不在 meta 行 → 检查 1 必须红 ----
    body = report(omit_stop_in_meta=True, mention_stop_in_prose=True)
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("block_mention_not_declaration", c == 1 and "检查1" in o, f"exit={c}")

    # ---- 14. 不认识的文件 → exit 2 ----
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": "只有一段散文，没有标题也没有 meta 行。\n"},
               ["--skill", SK, "{TMP}/r.md"])
    case("exit2_not_a_report", c == 2, f"exit={c}")

    # ---- 15. pre-contract 标记 → 跳过，且不得因此变红 ----
    body = "<!-- pre-contract -->\n" + report(omit_stop_in_meta=True)
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("pass_precontract_marker", c == 0 and "跳过" in o, f"exit={c}")

    # ---- 16. 标记只在第 11 行 → 不该豁免（行首锚定有牙）----
    body = "\n" * 10 + "<!-- pre-contract -->\n" + report(omit_stop_in_meta=True)
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("block_marker_outside_head", c == 1, f"exit={c}")

    # ---- 17. --all：legacy 降级 + 分桶互斥 + 计数正确 ----
    c, o = run(
        {"SKILL.md": GOOD_SKILL,
         "d/old1-survey.md": report(omit_stop_in_meta=True),
         "d/old2-survey.md": report(omit_stop_in_meta=True),
         "d/new-survey.md": report(),
         "d/marked-survey.md": "<!-- pre-contract -->\n# x\n> meta\n"},
        ["--skill", SK, "--all", "{TMP}/d"],
    )
    ok = c == 0 and "扫描 4" in o and "new 1" in o and "legacy 2" in o and "skipped 1" in o
    case("all_legacy_downgrade_and_buckets", ok, f"exit={c} :: {o.strip().splitlines()[-1] if o.strip() else ''}")

    # ---- 18. --all 指向不存在的目录 → exit 2（反真空，禁零用例假绿）----
    c, o = run({"SKILL.md": GOOD_SKILL}, ["--skill", SK, "--all", "{TMP}/nope"])
    case("exit2_all_dir_missing", c == 2, f"exit={c}")

    # ---- 19. --all 目录里没有 *-survey.md → exit 2 ----
    c, o = run({"SKILL.md": GOOD_SKILL, "d/other.md": "x"}, ["--skill", SK, "--all", "{TMP}/d"])
    case("exit2_all_no_survey_files", c == 2, f"exit={c}")

    # ---- 19b. 章节用裸编号（无 `##`）也必须能定位 → 容错有牙 ----
    # 骨架原写裸编号、86 份历史报告都写 `##`；两种都必须能读到 §5，否则
    # 「SUFFICIENT × 可动作缺口」这条互斥判据在裸编号报告上会静默失效。
    body = re.sub(r"^## ", "", report(), flags=re.M)
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("pass_bare_numbered_sections_readable", "未找到" not in o, f"exit={c} :: {o.strip()[:90]}")

    # ---- 19c. 别名节名（`## 5. 缺口清单`）必须同样可读 —— 否则检查 3 在真实产物上瞎 ----
    # 2026-09-25 pilot 实测：子进程因骨架把 §5 限 L3/L4 而自造了节名「缺口清单」，
    # 校验器按「缺口裁决表」找不到 → 检查 3 静默降级成 WARN。两条路径都要能咬。
    body = report(stop="SUFFICIENT", gaps=GAPS_ACTIONABLE_ALIAS)
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("block_alias_section_still_bites",
         c == 1 and "检查3" in o and "互斥" in o, f"exit={c} :: {o.strip()[:90]}")

    # ---- 19d. 声明数与缺口表行数不符 → 交叉核对必须报（pilot 实测新增的检查）----
    body = report(stop="TIER_LIMIT", gaps=GAPS_ACTIONABLE, **L2_LEDGER,
                  extra_meta="> ⚠️ 可动作缺口 9 条 · 建议升档 L3\n")
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("warn_declared_n_mismatch", c == 1 and "声明数" in o, f"exit={c} :: {o.strip()[:90]}")

    # ---- 19e. 台账值被 markdown 加粗 → 仍须能解析 ----
    # 2026-09-25 L2 pilot 实测：真实报告写 `搜索 **11/15** · 抓取 **10/10**` 与 `×B**1**`，
    # 正则不容忍 `*` 会把一份**实际合规**的报告判 BLOCK × 2。
    body = report()
    body = re.sub(r"(搜索 )(\d+/\d+)", r"\1**\2**", body)
    body = re.sub(r"(抓取 )(\d+/\d+)", r"\1**\2**", body)
    body = body.replace("×B1", "×B**1**")
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("pass_bold_emphasis_in_ledger", c == 0, f"exit={c} :: {o.strip()[:90]}")

    # ---- 20. 缺 §5 节 → 检查 3 报 WARN 而非 BLOCK（有发现则 exit 1，但 BLOCK 计数须为 0）----
    body = re.sub(r"## 5\. 缺口裁决表.*?(?=6\. 推荐结论)", "", report(), flags=re.S)
    c, o = run({"SKILL.md": GOOD_SKILL, "r.md": body}, ["--skill", SK, "{TMP}/r.md"])
    case("warn_missing_section5", c == 1 and "WARN" in o and "BLOCK 0" in o, f"exit={c} {o.strip()[:90]}")

    # ---- 报表 ----
    n_fail = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    for name, st, note in RESULTS:
        mark = "✅" if st == "PASS" else "🔴"
        print(f"{mark} {st:4} {name}" + (f"  [{note}]" if st == "FAIL" else ""))
    print(f"\n{len(RESULTS)} 例 · PASS {len(RESULTS) - n_fail} · FAIL {n_fail}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
