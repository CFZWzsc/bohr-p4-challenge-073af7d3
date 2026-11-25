# 快速开始（示例）

本目录是**合成演示**，用于验证接口与复核流程，不是平台固定案例的正式结果，也不描述任何真实研究。

## 1. 运行

在 `06_code/submission` 目录下：

```bash
python3 scripts/sk_entry.py \
  --input examples/demo-case \
  --work /tmp/demo-work \
  --out /tmp/demo-out
```

Windows PowerShell：

```powershell
python scripts/sk_entry.py --input examples/demo-case --work .\demo-work --out .\demo-out
```

等价薄封装：

```bash
python scripts/run_skill.py --input examples/demo-case --work /tmp/demo-work --out /tmp/demo-out
```

也可直接给结果文件路径：

```bash
python scripts/sk_entry.py --input examples/demo-case --out /tmp/demo-out/result.json
```

退出码应为 0。若 `--out` 不可写，脚本回退到 `--work/result.json`。

## 2. 示例输入

`examples/demo-case/case.json`（合成数据）：

| 记录 | 年份 | 内容 | 设计意图 |
|---|---|---|---|
| `R1` | 2019 | CAR-T 持久化与细胞因子 | 早期主题 |
| `R2` | 2020 | 细胞因子谱与持久化 | 早期主题延续 |
| `R3` | 2021 | CRISPR 筛选持久化调控因子 | 生长主题，批内高引用 |
| `R4` | 2021 | 长期持久化观察 | 同年后发记录 |
| `R5` | 2023 | 持久化开放问题 | 触发开放问题线索 |
| `R6` | 2024 | CRISPR + 机器学习 | 触发合并候选 |
| `R7` | 2025 | 机器学习设计 guide | 最新记录 |
| `R8` | 无 | CAR-T 制造评论 | 展示无年份记录的排除与人工确认 |

`output_contract` 含 10 个字段。

## 3. 期望输出要点

数值以实际运行为准，结构应一致：

- `status = success`，`case_id = demo-trend-001`；
- `trend_overview.year_counts` 为 `{"2019":1,"2020":1,"2021":2,"2023":1,"2024":1,"2025":1}`，`peak_year = 2021`；
- `terms` 10 项，含 `crispr`（growing）、`persistence`（declining）、`machine`（emerging）、`cohort` 与 `cytokine`（dormant）；
- `theme_evolution` 的 `stage` 与 `lifecycle_label` 一一对应；
- `conflicts` 含 `diverging_term_lifecycles`、至少一条 `candidate_merge` 与一条 `candidate_split`；
- `claim_evidence` 覆盖 `trend`、`evolution`、`representative`、`gap` 四类，`quote_verified` 全为 `true`；
- `gap_exclusion` 每条都有 `search_scope` 与 `exclusion_evidence`；
- `evidence_matrix` 8 行，`R8` 的 `included_in_series=false`；
- `flow = {identified:8, duplicates:0, unique:8, dated:7, undated:1}`；
- `review_report` 为四段中文叙事，`char_count >= 200`；
- 10 个契约键全部位于顶层，`not_determinable` 为空；
- 输出目录另有 `trend_stats.json`、`screening_log.csv`、`report.md`，且都登记在顶层 `artifacts`。

完整示意结果见 `examples/demo-case/example-result.json`（合成演示，标注 TOY，不可当作平台案例结论）。

## 4. 复核

1. 取 `claim_evidence[0].locator` 与 `quote`，在 `case.json` 中逐字比对。
2. 用 `evidence_matrix` 的 `included_in_series=true` 行复算 `year_counts`，并与 `trend_stats.json` 的 `year_histogram`、`screening_log.csv` 的 `decision=include` 对齐。
3. 抽查 `crispr`：首见 2021、提及 3 次、后半段 ≥2 次 → `growing`。
4. 抽查 `cohort`：最后出现 2021，距批末 2025 为 4 年 → `dormant`。
5. 确认 `candidate_merge` 只以候选措辞出现，未写成已确认合并。
6. 检查 `theme_evolution[].merge_rule.source` 是否为 `input`/`lexicon`/`term-level`，以及 `merge_evidence` 的词项。
7. 用相同命令再跑一次，确认 `result.json` 字节一致。

## 5. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `status=partial` | 有年份记录 <2 或年份跨度 =1 | 补充年份或扩大时间窗；不要放宽判定 |
| 词项为空或很少 | 标题/摘要过短或高度多样 | 查看 `research_gaps.thin_term_signal`，补充材料后再判 |
| 某主题被判 `dormant` | 最近 3 年无该词记录 | 属批界观察；查看 `gap_exclusion`，勿写成领域衰退 |
| `synthesis.direction=mixed` | 同时存在扩张与收缩词项 | 预期行为；分主题阅读 `theme_evolution` |
| 契约键出现 `not_determinable` | 该键无法从本批数据推导 | 按 `next_action` 在复核阶段补充，不得伪造 |
| `status=failed` | `case.json` 损坏或非对象 | 修正输入；失败结果仍保留全部契约键并 exit 0 |
