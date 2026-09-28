# open-skills

面向 [Claude Code](https://claude.com/claude-code) 的开源技能集。每个子目录是一个独立技能，放进 `~/.claude/skills/` 即可使用。

## 安装

```bash
git clone https://github.com/douxt/open-skills.git ~/open-skills
ln -sfn ~/open-skills/gale-research ~/.claude/skills/gale-research
```

Claude Code 启动时加载 `~/.claude/skills/*/SKILL.md`，此后可用 `/gale-research` 显式调用，或按 description 自动触发。

> - 直接 `git clone` 到 `~/.claude/skills/<技能名>` 也可以（那就无需 symlink）。
> - Windows 用 junction：`cmd //c mklink //J "%USERPROFILE%\.claude\skills\gale-research" "%USERPROFILE%\open-skills\gale-research"`（Git Bash 下 flag 必须写双斜杠）。
> - 技能是纯文档 + 可选脚本，改完立即生效（description 是会话启动时的快照，重启会话后更新）。

## 技能列表

| 技能 | 用途 |
|---|---|
| [gale-research](gale-research/) | 风力递进式网络调研：L1~L4 四档预算，产出带引用、可证伪的对比报告 |

## gale-research 使用要点

- **默认 L4** 是最深档（成本约 **30 次搜索 + 20 次抓取**）。轻量需求请说「随便看看 / L1」或「浅一点 / L3」。
- 说「N 倍预算」可放大当前档配额（clamp ×1~×5）。
- 报告落盘到当前项目的 `docs/references/<topic>-survey.md`；L1 默认不落盘，只交结论。
- 报告带**逐轮预算台账**与**停止原因**声明（`STOP=SUFFICIENT` / `BUDGET_EXHAUSTED` / `TIER_LIMIT` / `NO_PROGRESS` / `CONTRADICTION_UNRESOLVED`）。
- 默认 AFK 一次跑完；要每轮确认就说「每轮确认」。

### 工具（可选，需要 python3，无第三方依赖）

```bash
# 报告契约校验：停止码合法性 / 台账可解析 / 互斥规则
python3 gale-research/tools/check_gale_report.py <报告.md>
python3 gale-research/tools/check_gale_report.py --all <目录>

# 校验器自身的回归测试（30 例）
python3 gale-research/tools/selftest.py
```

⚠️ 校验器只检查报告的**自洽性与声明完整性**，**不校验所报数字与 URL 是否真实** —— `exit 0` 不等于内容为真。

## 镜像

- **GitHub（主）**：<https://github.com/douxt/open-skills>
- **Gitee（国内镜像）**：<https://gitee.com/douxt/open-skills>

Gitee 侧由 GitHub Actions 自动镜像推送，**单向**。**Issue 与 PR 请提到 GitHub** —— Gitee 侧不接受任何提交。

## License

[MIT](LICENSE)
