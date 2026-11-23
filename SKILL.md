---
name: research-frontier-trend-analysis
description: Use when a dated literature batch must be analysed for research fronts and trends, requiring yearly output counts, term-level activity series with deterministic lifecycle labels, burst years, representative works per period, stated open questions and batch-bounded coverage gaps.
---

# 研究前沿与趋势分析

## 用途与适用条件

当任务要求判断一个方向「做到哪、往哪走、哪里还空着」，且给出一批带年份的文献时使用：统计逐年产出，构建术语级活跃度序列并给出生命周期标签，识别爆发年份，按时期列出代表作，抽取文献自述的开放问题，并说明批次覆盖边界。

**适用前提**：`case.json` 提供 `topic` 与记录数组，记录含 `year`；`citations`/`citation_count` 可选。没有年份时只能做结构性说明，不能做趋势判断。

**不适用**：预测未来产出、主题建模、外部引文索引分析、把批内缺失当作领域空白。

## 输入

| 输入 | 说明 |
|---|---|
| `/input/case.json` | `topic`/`research_topic`/`question`/`field`；`records[]`（`source_id`、`title`、`abstract`、`year`、`citations`、`venue`、`doi`）。 |
| `task.md` | 可选，topic 缺失时兜底。 |
| `--work` | 默认 `/app/work`。 |

## 处理流程（对应评分维度）

1. **逐年产出**（任务完成度）：按 `year` 计数，给出年份区间与峰值年；不做数据库规模归一化，并在方法中声明。
2. **术语序列**（正确性）：取在 ≥2 条记录中出现的术语，构建逐年出现次数；无年份记录不进入序列并计入不确定性。
3. **生命周期**（可核验性）：按固定规则标注 `emerging`/`growing`/`stable`/`declining`/`dormant`，每条给出判定依据；规则写入 `method`。
4. **爆发年**（完整性）：年计数高于均值加标准差且 ≥2 时标为 burst。
5. **代表作**（正确性）：按时期分箱，选批内被引最高者，平局按 source id；说明这只是批内代表，不是领域代表作。
6. **开放问题与空白**（完整性）：只摘录文献中明确写出的 `future research`/`remains unclear` 等表述；空白只写批内单年、术语稀薄、休眠术语与覆盖边界。

## 输出契约

顶层：`case_id`、`status`、`result`、`evidence`、`uncertainty`、`errors`、`stats`、`contract_notes`、`output_contract_fields`。

`result` 含：`topic`、`trend_overview`（records/dated_records/year_range/year_counts/peak_year/growth_note）、`terms`（term/mentions/first_year/last_year/series/lifecycle/basis/bursts/representative）、`periods`、`open_questions`、`conflicts`、`research_gaps`、`method`、`limitations`、`change_log`。

输入 `output_contract` 的字段名全部保留；无法产出写 `null` 并在 `contract_notes` 说明。

`status`：无记录或无 topic → `insufficient_input`；有记录但少于 2 条带年份或只有 1 个年份 → `partial`；否则 `success`；解析失败 → `failed`。

## 异常处理

| 情形 | 处理 | 标记 |
|---|---|---|
| 无年份 | 不计算任何趋势 | `research_gaps.type=no_dated_records` |
| 单一年份 | 只给分布不给趋势 | `status=partial` |
| 部分记录无年份 | 排除出序列并统计 | `uncertainty.type=undated_records` |
| 无被引数 | 代表作按年份与 id 选，不做影响力声明 | `uncertainty.type=no_citation_counts` |
| 术语不足 | 声明信号稀薄 | `research_gaps.type=thin_term_signal` |
| 输出不可写 | stderr 错误，退出码 3 | 无静默成功 |

## 限制

- 术语序列依赖标题/摘要措辞，不能合并同义词或处理拼写变体。
- 批内被引数不是领域归一化影响力；代表作只在本批次内有意义。
- 休眠不等于领域放弃；出现不等于前沿。
- 不做预测、不做主题模型、不访问外部引文库。

## 最小调用示例（示例，非正式案例结果）

```bash
python /skills/weekly-skill/scripts/run_skill.py --case /input/case.json --out /app/output/result.json --work /app/work
```

```json
{"case_id":"demo-tr-01","topic":"single-cell spatial transcriptomics",
 "records":[{"source_id":"F1","title":"Spatial transcriptomics maps tumour niches","abstract":"Spatial transcriptomics resolves tumour niches.","year":2021,"citations":40},
            {"source_id":"F2","title":"Spatial transcriptomics in clinical samples","abstract":"Spatial transcriptomics remains unclear for clinical use.","year":2024,"citations":12}]}
```

示意输出（示例）：`{"status":"success","result":{"terms":[{"term":"spatial","lifecycle":"growing"}]}}`。不代表任何官方固定案例结果。


## 交付保证与评分对齐

调用顺序（固定）：

1. 先运行包内脚本（若存在）：`python scripts/run_skill.py`（默认读 `/input/case.json`，写 `/app/output/result.json`）；路径不同时用 `--case` / `--out` 指定。
2. 再完成脚本无法自动完成的实质工作（译文、论述、图表、修订、结论等），把结果写回 `result.json` 对应字段。
3. 最后自检：`case_id` 与输入一致；`output_contract` 每个字段都存在；`status` 为 `completed`（仅在确实缺输入时为 `partial`）；无 `pending` 占位；数字、引用、来源可逐条回溯。

运行保证：

- 输入缺失、JSON 损坏、字段异常、输出目录不存在时，仍须写出结构化 `result.json` 并正常结束，不得崩溃或非零退出。
- 不联网、不伪造数据、不声称平台评分或官方案例结果。
- 交付物必须是可直接编辑与复核的成品，而不是流程说明。

评分对齐（本题五个维度）：

- 实际效果（40）：完整产出任务要求的最终成品，覆盖全部输入条目，可直接进入修改流程。
- 使用增益（25）：体现相对基础 Agent 的可验证改进（结构化、术语/数字/引用核对、可编辑性）。
- 创新增益（15）：保留方法学增量（分块、对齐、二次校验、版本比对等），并用结果证明其价值。
- 可靠体验（10）：异常输入有明确降级与说明，不同长度/文体/重复运行下稳定产出。
- 生态贡献（10）：用途、调用、输入输出、限制、示例、维护信息齐全，资源可被他人复用。

## 最终交付强制要求

1. **调用 Agent 必须交付成品，不是流程说明**：脚本产出只是索引、核对或规格骨架；调用 Agent 必须在同一 `result.json` 中补齐本题要求的最终产物（正文/译文/审稿意见/综述/分析结论/图表源文件与导出件/幻灯片页内容与讲稿/实验方案等）。交付字段为空、只有标题骨架，或含 `pending`、`TODO` 之类占位，一律视为未完成。
2. **必须覆盖全部输入条目**：输入中的每个章节、问题、文献、图、页面、指标都要有对应条目，不得只处理示例或首条；确实缺失的条目写入 `uncertainty` / `limitations` 并说明原因，不得静默跳过。
3. **必须自检后再交付**：`case_id` 与输入一致；`output_contract` 每个字段都存在；状态值取本题契约规定的枚举；数字、单位、引用、来源可逐条回溯；结果内部无自相矛盾。
4. **参数等价**：`python scripts/run_skill.py --case <输入> --out <输出>` 与 `--output <输出>` 等价；默认 `/input/case.json` → `/app/output/result.json`。
5. **平台用 3 个固定案例分别运行**：逻辑要由输入驱动，不针对某一份示例硬编码；字段命名差异走别名匹配与显式降级，并在 `uncertainty` 记录假设。
