# 文献趋势分析 Skill（challenge-073af7d3）

在给定文献批次上做趋势分析：时间切片、主题演化、每阶段代表作、研究空白，并产出可独立复算的统计表与可回溯的证据。

## 输入

- `--input <dir>`：包含 `case.json`（`records` / `task` 等），可选包含真实原文材料（`*.md` / `*.txt` / `*.csv` / `*.json`；PDF 需 `pdftotext`）。原文按标题/DOI 匹配到题录，证据定位到 `S3#P7`。
- `--work <dir>`：工作目录（默认 `/app/work`）。
- `--out <dir|file.json>`：输出位置（默认 `/app/output`）。

## 运行

```bash
python -B scripts/run_skill.py --input /input --work /app/work --out /app/output
```

## 输出

`result.json` 顶层含 `case_id`、`status`、`result`（`trend_overview`、`periods`、`theme_evolution`、`representative_selection`、`research_gaps`、`retrieval_scope`、`review_report` 等）、`evidence`、`uncertainty`、`errors`、`stats`、`contract_notes`；并写出 `trend_stats.json`、`screening_log.csv`、`report.md`。

## 限制

- 只在提供的批次上统计，不联网；`hits_per_query` 为离线命中计数并已注明。
- 主题归并优先使用输入声明的 `concept_rules`；无声明时回退 `assets/theme-lexicon.json` 并标注 `merge_basis`。
- 重复题录按 DOI 或归一化标题+年去重，`flow` 做算术闭合。
- `examples/example-result.json` 为合成 demo，不代表官方案例结果。

## 文件

- `SKILL.md`、`scripts/sk_entry.py`、`scripts/run_skill.py`
- `assets/policy.json`、`assets/theme-lexicon.json`（fallback 词表）
- `references/`、`examples/demo-case/`、`examples/example-result.json`
- `requirements.txt`
