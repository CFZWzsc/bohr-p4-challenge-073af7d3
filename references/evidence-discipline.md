# 证据定位与不编造纪律

本文件规定趋势结论如何回到原文，以及哪些话在这类分析中不能说。脚本只做确定性统计，可信度取决于每条判断能否被独立复核。

## 1. 定位符（locator）

- 统一使用 `case.json` 的 JSON Pointer：`/records/0`、`/papers/3`、`/sources/2`。
- 不使用生成报告的页码、图号或自建编号。
- 主题来自 `task.md` 时，读取方式记录在 `retrieval_scope.task_text_used=true`。
- 记录缺 `source_id` 时按 `F01` 起编号，但 `locator` 仍指向真实位置。

## 2. 引文（quote）

- `quote` 必须是指定字段的精确子串，不改写、不加省略号、不拼接多个字段。
- 超长截取前缀，`truncated=true`；`quote_verified` 记录子串校验结果。
- 只有标题的记录可以引用标题，但必须说明没有摘要，相关比较视为受限。

## 3. 三类陈述分开

| 类型 | 写法 | 落点 |
|---|---|---|
| 材料事实 | 有 `locator` + `quote` | `evidence`、`evidence_matrix`、`claim_evidence`、`open_questions` |
| 合理推断 | 由本批统计推出并写明口径 | `trend_overview`、`theme_evolution`、`synthesis`、`research_gaps` |
| 无法确定 | 写明缺什么、谁来判断 | `needs_human_confirmation`、`uncertainty` |

不得把第三类写成第一类。

## 4. 禁止事项

- 不编造文献、年份、期刊、DOI、引用数或开放问题原文。
- 不把「本批没出现」写成「领域空白」；只能写 `not_found_in_batch` 或 `batch_coverage`。
- 不把关键词频次上升直接写成「新兴主题」；必须给出首见年与前后半段计数。
- 不把引用数最高直接写成「代表作」；必须说明这是**批内**引用口径及遗漏。
- 不把共现候选写成已确认的合并或分裂。
- 不预测未来年份、增长率或成熟度。

## 5. 时间口径

- 年份按输入原样使用；不区分在线发表、见刊与预印本，这一点写入 `limitations`。
- 无年份记录不得被静默丢弃：进入 `evidence_matrix`（`included_in_series=false`、`exclusion_reason`）与 `needs_human_confirmation`。
- 单年批不产出趋势结论，只产出计数与明确的 `single_year_batch` 空白。

## 6. 空白（gap）的写法

- 每条空白要有 `search_scope`（记录数、年份范围、检查的词项）与 `exclusion_evidence`。
- 说明是「无有年份记录」「单年批」「休眠词项」「词项信号过薄」还是「批覆盖边界」。
- 不把检索式、数据库覆盖或语言限制的不足写成领域空白。

## 7. 复核步骤

1. 取 `claim_evidence[0]`，按 `locator` 打开 `case.json`，逐字比对 `quote`。
2. 用 `year_counts` 复算峰值年与前后半段计数。
3. 抽查一个 `emerging` 词项：首见年、总提及、后半段计数是否满足规则。
4. 抽查一个 `dormant` 词项：最后出现年与批末的间隔是否 ≥3 年。
5. 抽查 `periods`：代表工作是否为该区间批内引用最高。
6. 检查所有 `candidate_merge` / `candidate_split` 措辞是否仍为候选。
7. 检查无年份记录是否出现在 `evidence_matrix` 与 `needs_human_confirmation`。

## 8. 输入边界

- 除 `case.json` 记录外不解析其他材料文件；其他文件仅登记到 `input_manifest`。
- 不联网、不调用外部模型；所有数字可由同一脚本复跑复现。
- 不读取或输出任何令牌、密钥、账号信息或个人路径。
