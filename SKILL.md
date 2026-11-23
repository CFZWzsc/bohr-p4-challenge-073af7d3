---
name: research-frontier-trend-analysis
description: Use when a dated literature batch must be analysed for research fronts and trends: yearly counts, term activity with deterministic lifecycle labels, bursts, representative works, stated open questions and batch-bounded gaps.
---

# 研究前沿与趋势分析

## 用途与适用条件

判断一个方向“做到哪、往哪走、哪里还空着”：统计逐年产出，构建术语活跃度序列与生命周期，识别爆发年，按时期选代表作，抽取文献自述开放问题，并声明批次边界。

- 适用前提：`case.json` 提供 `topic` 与记录数组，记录含 `year`；`citations` 可选。无年份只能做结构性说明，不能做趋势判断。
- 不适用：预测未来产出、主题建模、外部引文索引分析、把批内缺失当作领域空白。

## 输入

| 输入 | 说明 |
|---|---|
| `/input/case.json` | `topic`/`research_topic`/`question`/`field`；`records[]`（`source_id`、`title`、`abstract`、`year`、`citations`、`venue`、`doi`） |
| `task.md` | 可选；topic 缺失时兜底 |
| `--work` | 默认 `/app/work` |

## 处理流程

1. **逐年产出**：按 `year` 计数，给年份区间与峰值年；不做数据库规模归一化并声明。
2. **术语序列**：取在 ≥2 条记录出现的术语，逐年计数；无年份记录不入序列并计入不确定性。
3. **生命周期**：按固定规则标 `emerging`/`growing`/`stable`/`declining`/`dormant`，每条给判定依据，规则写入 `method`。
4. **爆发年**：年计数高于均值加标准差且 ≥2 时标 `burst`。
5. **代表作**：按时期分箱，选批内被引最高者，平局按 `source_id`；声明这只是批内代表。
6. **开放问题与空白**：只摘录文献明写的 `future research`/`remains unclear`；空白只写批内单年、术语稀薄、休眠与覆盖边界。

## 输出契约

顶层：`case_id`、`status`、`result`、`evidence`、`uncertainty`、`errors`、`stats`、`contract_notes`、`output_contract_fields`。

`status`：无记录或无 topic → `insufficient_input`；带年份记录 <2 或只有 1 个年份 → `partial`；否则 `success`；解析或运行失败 → `failed`（唯一枚举）。

`result` 必含：`topic`、`trend_overview`、`terms`、`periods`、`open_questions`、`conflicts`、`research_gaps`、`method`、`limitations`、`change_log`。调用 Agent 必须补齐（`output_contract` 声明时置于顶层，否则并入 `result`）：

| 字段 | 内容 |
|---|---|
| `retrieval_scope` | `query`/`inclusion`/`exclusion`/`batch_size`；声明批次不是全领域检索 |
| `claim_evidence[]` | `claim`、`source_ids`、`locator`、`quote`、`period`，覆盖趋势、演化、代表作、空白四类判断 |
| `theme_evolution[]` | `theme`、`stage`（`appear`/`merge`/`split`/`decline`）、`from_year`、`to_year`、`basis`（触发变化的记录） |
| `representative_selection` | 每时期 `period`、`rule`、`covered_stages`、`known_omissions` |
| `gap_exclusion` | 每个空白主张的 `search_scope` 与排除证据，防止把检索遗漏写成空白 |
| `needs_human_confirmation[]` | `item`、`locator`、`reason` |

输入 `output_contract` 每个字段名写到顶层；脚本未产出者置 `null` 并记 `contract_notes`，调用 Agent 用真实结果替换，确无法产出才保留 `null`。

## 证据要求

- `evidence`/`claim_evidence` 每条含 `source_id`、`locator`（输入 JSON Pointer，如 `/records/3`）、`quote`；不把自建图页序当原文页码。
- 结论必须由本批统计支撑；无法支撑或与记录冲突时写 `conflicts` 或 `needs_human_confirmation`，不补造年份、被引数或文献。
- `research_gaps` 必须附排除条件；批内缺失不等于领域空白。

## 异常处理

| 情形 | 处理 | 标记 |
|---|---|---|
| 无年份 | 不计算任何趋势 | `research_gaps.type=no_dated_records` |
| 单一年份 | 只给分布，不给趋势 | `status=partial` |
| 部分记录无年份 | 排除出序列并计数 | `uncertainty.type=undated_records` |
| 无被引数 | 代表作按年份与 id 选，不做影响力声明 | `uncertainty.type=no_citation_counts` |
| 术语不足 | 声明信号稀薄 | `research_gaps.type=thin_term_signal` |
| 生命周期方向冲突 | 同时报告，不强行给单一方向 | `conflicts.type=diverging_term_lifecycles` |
| 输出不可写 | stderr 报错，退出码 3 | 无静默成功 |

## 限制

术语序列依赖标题/摘要措辞，不合并同义词或拼写变体；批内被引不是领域归一化影响力；休眠不等于领域放弃，出现不等于前沿；不做预测、主题模型或外部引文库访问。

## 最小调用示例（示例，非正式案例结果）

```bash
python /skills/weekly-skill/scripts/run_skill.py --case /input/case.json --out /app/output/result.json --work /app/work
# --output 与 --out 等价
```

```json
{"case_id":"demo-tr-01","topic":"single-cell spatial transcriptomics","records":[{"source_id":"F1","title":"Spatial transcriptomics maps tumour niches","abstract":"Spatial transcriptomics resolves tumour niches.","year":2021,"citations":40},{"source_id":"F2","title":"Spatial transcriptomics in clinical samples","abstract":"Spatial transcriptomics remains unclear for clinical use.","year":2024,"citations":12}]}
```

示意输出（示例）：`{"status":"success","result":{"terms":[{"term":"spatial","lifecycle":"growing"}]}}`。不代表任何官方固定案例结果。

## 交付与自检

1. **交付四类产物**：时间趋势、主题演化、代表性工作、研究空白都要有实质内容，不能只有骨架或 `pending`/`TODO`。
2. **逐条回溯**：每个趋势/演化/空白判断都有 `locator` + `quote`；数字来自本批统计。
3. **契约自检**：`case_id` 与输入一致；`output_contract` 每字段存在；`status` 只取四个枚举；重复运行结果相同。
4. **输入驱动**：不针对示例硬编码；年份缺失或主题歧义显式降级并记录；不联网、不声称官方评分。
