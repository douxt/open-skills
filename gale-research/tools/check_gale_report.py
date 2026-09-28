#!/usr/bin/env python3
"""check_gale_report.py —— gale-research 报告契约校验器（切片 1 · 核心 6 项）

校验一份调研报告是否满足 gale-research SKILL.md 的「停止原因 + 逐维预算台账」契约。

用法:
    python check_gale_report.py <报告.md>
    python check_gale_report.py --all <目录>          # 扫 *-survey.md
    python check_gale_report.py --skill <SKILL.md> <报告.md>   # 覆盖档位表来源

退出码: 0 通过 / 1 有发现 / 2 这不是 gale 报告（或档位表无法解析）

=====================================================================
🔴 诚实边界（必读 —— 决定这些结论能用到哪）
=====================================================================
本脚本校验的是报告的**自洽性与声明完整性**，不是所报数字的真伪。

**它做不到**：
  - 不校验报告自报的用量是否等于真实发生的工具调用数（自报↔行为落差）
  - 不校验某个 URL 是否真的支撑它旁边那句声明
  - 不校验候选清单/排除清单是否完整
  - 不校验「逐个候选写落选理由」是否真的逐候选执行过（那是散文语义）
  - 不判断阈值本身是否合理（档位基准、B 的 clamp 区间均由 SKILL.md 定义）

🔴 **覆盖率披露**：本脚本只实现切片 1 的**核心 6 项（检查 1–6）**。
检查 8（预留绝对下限）/ 9（§5 行格式）/ 10（骨架）/ 11（URL 下限）/
12（TODO·密钥）/ 13（`--all` 之外的批量）**未实现** ——
**`exit 0` 不得读作它们也已通过。**
其中「6 次调用」是**结构推导**、「50%/25%」是**设计选择** —— 二者都不是可校准量。

所以「本脚本 exit 0」只意味着**这份报告的声明是自洽的**，
不意味着**这份报告的结论是可靠的**。两者是不同的命题。

措辞纪律：只报「本节缺失 / 本规则被违反 N 次」，不写「本节很重要」。
=====================================================================
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 档位基准上限的期望值（与 SKILL.md 量级契约表交叉校验 —— 不等即 exit 2）
EXPECTED_BASE = {"L1": (8, 0), "L2": (15, 10), "L3": (22, 15), "L4": (30, 20)}

STOP_CODES = {"SUFFICIENT", "BUDGET_EXHAUSTED", "TIER_LIMIT", "NO_PROGRESS", "CONTRADICTION_UNRESOLVED"}
# 补救方式不同的两类：BUDGET_EXHAUSTED 加预算（同档位），TIER_LIMIT 升档（加钱无用）
NEEDS_GAP_N = ("BUDGET_EXHAUSTED", "TIER_LIMIT")

PRECONTRACT_MARK = "<!-- pre-contract -->"
PRECONTRACT_HEAD_LINES = 10

TIER_ROW_RE = re.compile(r"^\|\s*(L\d)\b.*$")
CAP_RE = re.compile(r"~?\s*(\d+)\s*/\s*~?\s*(\d+)\s*$")

META_STOP_RE = re.compile(r"停止原因\s*[:：]\s*STOP=([A-Z_]+)")
TIER_RE = re.compile(r"档位\s*(L\d)")
LEDGER_MARK = "用量台账"
LEDGER_S_RE = re.compile(r"搜索\s*(\d+)\s*/\s*(\d+)")
LEDGER_F_RE = re.compile(r"抓取\s*(\d+)\s*/\s*(\d+)")
LEDGER_B_RE = re.compile(r"×\s*B\s*(\d+(?:\.\d+)?)")
ROUND_RE = re.compile(r"R(\d+)\s*搜索\s*(\d+)\s*/\s*抓取\s*(\d+)")
GAP_N_RE = re.compile(r"可动作缺口\s*(\d+)\s*条")
MULT_RE = re.compile(r"建议倍率\s*×\s*(\d+(?:\.\d+)?)")
UPGRADE_RE = re.compile(r"建议升档\s*L(\d)")

ACTIONABLE = "未闭合·可动作"


class Finding:
    def __init__(self, sev: str, check: str, msg: str):
        self.sev, self.check, self.msg = sev, check, msg


def parse_tier_base(skill_path: Path) -> dict[str, tuple[int, int]] | None:
    """解析 SKILL.md 的档位契约表 → {档位: (搜索上限, 抓取上限)}。失败返回 None。"""
    try:
        text = skill_path.read_text(encoding="utf-8")
    except OSError:
        return None
    out: dict[str, tuple[int, int]] = {}
    for line in text.splitlines():
        m = TIER_ROW_RE.match(line.strip())
        if not m:
            continue
        cells = line.split("|")
        if len(cells) < 3:
            continue
        cap = CAP_RE.search(cells[-2].strip())
        if not cap:
            continue
        out[m.group(1)] = (int(cap.group(1)), int(cap.group(2)))
    return out or None


# 章节写法收两种：`## 5. 缺口裁决表` 与裸编号 `5. 缺口裁决表`。
# 骨架原写裸编号，而 86 份历史报告实际都带 `##` —— 两种都收。
# 裸编号只在「行首 + 含已知章节名」时才算章节起点，避免把正文里的「1. 第一点」误判。
KNOWN_SECTIONS = ("术语对照表", "候选对比总表", "排除清单", "关键技术判断",
                  "缺口裁决表", "缺口清单", "推荐结论", "来源列表")
# 「缺口清单」是别名：骨架原写「缺口裁决表(仅 L3/L4)」，而停止码要求全档位声明缺口
# ⇒ L1/L2 的实际作者会自造节名（源自实测：一份 L2 报告把该节写成了「缺口清单」）。
# 别名收着，但正名以 SKILL.md 骨架为准。
GAP_SECTIONS = ("缺口裁决表", "缺口清单")


def is_section_start(ln: str) -> bool:
    s = ln.strip()
    if not s:
        return False
    if s.startswith("#"):
        s = s.lstrip("#").strip()
    elif not re.match(r"^\d+\s*[.、)]", s):
        return False
    return any(k in s for k in KNOWN_SECTIONS)


def section_body(lines: list[str], heading_kw) -> list[str] | None:
    """取包含 heading_kw 的章节正文，直到下一个章节起点。heading_kw 可为 str 或候选元组。"""
    kws = (heading_kw,) if isinstance(heading_kw, str) else tuple(heading_kw)
    start = None
    for i, ln in enumerate(lines):
        if any(k in ln for k in kws) and is_section_start(ln):
            start = i + 1
            break
    if start is None:
        return None
    for j in range(start, len(lines)):
        if is_section_start(lines[j]):
            return lines[start:j]
    return lines[start:]


def check_report(path: Path, bases: dict[str, tuple[int, int]], legacy_ok: bool) -> tuple[int, list[Finding]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return 2, [Finding("BLOCK", "-", f"无法读取: {e}")]
    lines = text.splitlines()

    head = lines[:PRECONTRACT_HEAD_LINES]
    if any(ln.strip() == PRECONTRACT_MARK for ln in head):
        print(f"⏭  {path.name}: pre-contract 标记 → 跳过（豁免全部机检）")
        return 0, []

    f: list[Finding] = []
    meta_lines = [ln for ln in lines if ln.lstrip().startswith(">")]
    # 容忍 markdown 强调：模型很自然会把关键值加粗（`搜索 **11/15**`、`×B**1**`），
    # 而契约只说「格式固定」，并未禁止强调 —— 正则必须能穿过 `*` 与反引号。
    # ⚠️ 只去 `*` 与反引号，**不去 `_`**：停止码含下划线（BUDGET_EXHAUSTED），去掉会认不出。
    meta_flat = [ln.replace("*", "").replace("`", "") for ln in meta_lines]

    # 不是 gale 报告 → exit 2（反真空：宁报「不认识」，不给假绿）
    if not meta_lines and not any(ln.startswith("#") for ln in lines):
        return 2, [Finding("BLOCK", "-", "既无 meta 行也无标题 —— 不像调研报告")]

    # ---- 检查 1：停止原因（只在 meta 行认，正文提到不算）----
    stop = None
    for ln in meta_flat:
        m = META_STOP_RE.search(ln)
        if m:
            stop = m.group(1)
            break
    if stop is None:
        sev = "WARN" if legacy_ok else "BLOCK"
        f.append(Finding(sev, "1", "meta 行缺 `停止原因: STOP=<码>`（正文提到不算）"))
    elif stop not in STOP_CODES:
        f.append(Finding("BLOCK", "1", f"停止码 `{stop}` 不在契约枚举内（{sorted(STOP_CODES)}）"))

    # 声明数（检查 2 与检查 3 的交叉核对共用）
    declared_n = None
    for ln in meta_flat:
        m = GAP_N_RE.search(ln)
        if m:
            declared_n = int(m.group(1))
            break

    # ---- 检查 2：带缺口的停止码必须写齐额外字段（两类补救方式不同）----
    if stop in NEEDS_GAP_N:
        n = declared_n
        if n is None or n < 1:
            f.append(Finding("BLOCK", "2", f"STOP={stop} 但缺 `可动作缺口 N 条`（N≥1）"))
        if stop == "BUDGET_EXHAUSTED":
            mm = None
            for ln in meta_flat:
                m = MULT_RE.search(ln)
                if m:
                    mm = float(m.group(1))
                    break
            if mm is None or mm < 2:
                f.append(Finding("BLOCK", "2", "STOP=BUDGET_EXHAUSTED 但缺 `建议倍率 ×M`（M≥2）"))
        else:
            if not any(UPGRADE_RE.search(ln) for ln in meta_flat):
                f.append(Finding("BLOCK", "2",
                                 "STOP=TIER_LIMIT 但缺 `建议升档 L<n>`"
                                 "（本档结构上已无更多轮次，加预算无用）"))

    # ---- 检查 3：SUFFICIENT 与「未闭合·可动作」互斥 + 声明数交叉核对 ----
    gaps = section_body(lines, GAP_SECTIONS)
    if gaps is None:
        f.append(Finding("WARN", "3", "未找到「缺口裁决表」节 —— 无法核对停止码与缺口状态"))
    else:
        actionable_rows = [ln for ln in gaps if ln.strip().startswith("|") and ACTIONABLE in ln]
        if stop == "SUFFICIENT" and actionable_rows:
            f.append(Finding("BLOCK", "3",
                             f"STOP=SUFFICIENT 但缺口表有 {len(actionable_rows)} 行「{ACTIONABLE}」"
                             "（两者互斥：SUFFICIENT 要求不存在可动作缺口）"))
        if stop in NEEDS_GAP_N and declared_n is not None and actionable_rows \
                and declared_n != len(actionable_rows):
            f.append(Finding("WARN", "3",
                             f"声明数与缺口表不符：meta 写 {declared_n} 条，"
                             f"表内实有 {len(actionable_rows)} 行「{ACTIONABLE}」"))

    # ---- 检查 4：台账可解析 + 生效上限 == 档位基准 × B ----
    ledger_ln = next((ln for ln in meta_flat if LEDGER_MARK in ln), None)
    if ledger_ln is None:
        sev = "WARN" if legacy_ok else "BLOCK"
        f.append(Finding(sev, "4", "meta 行缺 `用量台账`"))
    else:
        ms, mf = LEDGER_S_RE.search(ledger_ln), LEDGER_F_RE.search(ledger_ln)
        mb = LEDGER_B_RE.search(ledger_ln)
        if not ms or not mf:
            f.append(Finding("BLOCK", "4", "台账缺逐维「搜索 已用/上限」或「抓取 已用/上限」"))
        if not mb:
            f.append(Finding("BLOCK", "4", "台账缺 `×B<值>`（含 ×1 也必须显式写出，否则无法判定上限口径）"))
        tm = None
        for ln in meta_flat:
            m = TIER_RE.search(ln)
            if m:
                tm = m.group(1)
                break
        if not ms or not mf or not mb:
            pass
        elif tm is None:
            f.append(Finding("BLOCK", "4", "缺「档位 L<n>」声明 —— 无法核对生效上限"))
        elif tm not in bases:
            f.append(Finding("BLOCK", "4", f"档位 `{tm}` 不在档位表中（{sorted(bases)}）"))
        else:
            b = float(mb.group(1))
            bs, bf = bases[tm]
            exp_s, exp_f = round(bs * b), round(bf * b)
            if int(ms.group(2)) != exp_s or int(mf.group(2)) != exp_f:
                f.append(Finding("BLOCK", "4",
                                 f"生效上限不符：台账写 {ms.group(2)}/{mf.group(2)}，"
                                 f"按 {tm} 基准 {bs}/{bf} ×B{b:g} 应为 {exp_s}/{exp_f}"))

        # ---- 检查 5：算术（逐维，不跨维合计）----
        rounds = ROUND_RE.findall(ledger_ln)
        if not rounds:
            f.append(Finding("BLOCK", "5", "台账缺 `逐轮: R<n> 搜索 x/抓取 y` —— 无法验证算术自洽"))
        elif ms and mf:
            ss = sum(int(r[1]) for r in rounds)
            sf = sum(int(r[2]) for r in rounds)
            if ss != int(ms.group(1)):
                f.append(Finding("BLOCK", "5", f"搜索维算术不符：Σ各轮 {ss} ≠ 台账已用 {ms.group(1)}"))
            if sf != int(mf.group(1)):
                f.append(Finding("BLOCK", "5", f"抓取维算术不符：Σ各轮 {sf} ≠ 台账已用 {mf.group(1)}"))

        # ---- 检查 6：超顶却报 SUFFICIENT ----
        if ms and mf and stop == "SUFFICIENT":
            over = []
            if int(ms.group(1)) > int(ms.group(2)):
                over.append(f"搜索 {ms.group(1)}>{ms.group(2)}")
            if int(mf.group(1)) > int(mf.group(2)):
                over.append(f"抓取 {mf.group(1)}>{mf.group(2)}")
            if over:
                f.append(Finding("BLOCK", "6", f"任维超顶却报 STOP=SUFFICIENT：{', '.join(over)}"))

    return (1 if f else 0), f


def main() -> int:
    ap = argparse.ArgumentParser(description="gale-research 报告契约校验器")
    ap.add_argument("report", help="报告文件，或 --all 时的目录")
    ap.add_argument("--all", action="store_true", help="扫目录下 *-survey.md")
    ap.add_argument("--skill", default=None, help="SKILL.md 路径（默认 ../SKILL.md）")
    args = ap.parse_args()

    skill_path = Path(args.skill) if args.skill else Path(__file__).resolve().parent.parent / "SKILL.md"
    bases = parse_tier_base(skill_path)
    if not bases:
        print(f"✗ 无法从 {skill_path} 解析档位契约表 —— 拒绝在未定义口径下判定（exit 2）")
        return 2
    if bases != EXPECTED_BASE:
        print(f"✗ 档位表与内建期望值不符（fail-closed）")
        print(f"   解析得: {bases}")
        print(f"   期望值: {EXPECTED_BASE}")
        print("   若确为有意调整档位，请同步更新脚本内的 EXPECTED_BASE 常量")
        return 2

    if args.all:
        d = Path(args.report)
        if not d.is_dir():
            print(f"✗ 目录不存在: {d}（拒绝零用例假绿，exit 2）")
            return 2
        files = sorted(d.glob("*-survey.md"))
        if not files:
            print(f"✗ {d} 下无 *-survey.md（拒绝零用例假绿，exit 2）")
            return 2
        n_new = n_legacy = n_skip = n_block = 0
        for p in files:
            txt = p.read_text(encoding="utf-8", errors="replace")
            skipped = any(ln.strip() == PRECONTRACT_MARK for ln in txt.splitlines()[:PRECONTRACT_HEAD_LINES])
            code, findings = check_report(p, bases, legacy_ok=True)
            blocks = [x for x in findings if x.sev == "BLOCK"]
            if skipped:
                n_skip += 1
            elif any(x.check == "1" and "缺" in x.msg for x in findings) and not blocks:
                n_legacy += 1
            else:
                n_new += 1
            n_block += len(blocks)
            for x in findings:
                print(f"  [{x.sev}] {p.name} · 检查{x.check}: {x.msg}")
        total = len(files)
        print(f"\n扫描 {total} · new {n_new} · legacy {n_legacy} · skipped {n_skip} · BLOCK {n_block}")
        if n_new + n_legacy + n_skip != total:
            print("✗ 分桶不互斥（内部错误）")
            return 2
        return 1 if n_block else 0

    code, findings = check_report(Path(args.report), bases, legacy_ok=False)
    if code == 2:
        print(f"✗ {args.report}: 这不是一份可识别的 gale 报告（exit 2）")
        return 2
    for x in findings:
        print(f"[{x.sev}] 检查{x.check}: {x.msg}")
    print(f"\n{'✅ 通过' if code == 0 else '⚠ 有发现'} — {args.report}（BLOCK {sum(1 for x in findings if x.sev=='BLOCK')} · WARN {sum(1 for x in findings if x.sev=='WARN')}）")
    return code


if __name__ == "__main__":
    sys.exit(main())
