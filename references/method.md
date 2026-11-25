# 方法与打分口径

本文件描述 `scripts/sk_entry.py` 实际执行的确定性算法。阈值来自 `assets/policy.json`，缺省值与脚本内置值一致。

## 1. 记录发现与归一化

- 优先读取 `records` / `papers` / `documents` / `literature` / `sources` / `items` / `known_works` / `prior_works` / `candidates` / `search_results` / `screening_records` / `bibliography` 中的对象数组。
- 若不存在，则递归查找含 `title`/`abstract`/`year`/`doi`/`authors` 的对象，深度上限 7，最多 2000 条。
- 归一化：`source_id`（缺失时 `F01` 起）、`locator`（`/<键>/<下标>`）、`title`、`abstract`、`year`、`citations`、`venue`、`doi`、`authors`。
- 年份取 1800–2100 的整数或文本中第一个四位年份；无法解析记为无年份，排除出所有按年统计，但仍参与开放问题提取与证据矩阵。
- 去重：先取 DOI（去 `doi:`/URL 前缀、小写），再取「归一化标题 + 年份」；任一键已出现即记为 `duplicate_of=<首条 source_id>`，并从所有年份序列中剔除。`flow.identified = duplicates + unique`，`unique = dated + undated`。
- 材料：扫描输入根下 `.md`/`.txt`/`.csv`/`.json`，按空行切段落并编号；PDF 调用本机 `pdftotext`，不可用或失败标 `status=unparsed`。记录按 DOI 或标题匹配段落，命中后 `locator=S<文件序号>#P<段落序号>`。

## 2. 年度分布

- `year_counts`：每个年份**去重后**的记录条数（绝对值，不按数据库规模归一）。
- `peak_year`：计数最大的年份；平票取较晚年份。
- 相邻年的计数差只用于描述，**不**判定拐点；拐点由第 4 节的突发年规则给出。

## 3. 词项与序列

1. 英文按 `[A-Za-z][A-Za-z0-9-]{2,}` 切词并去停用词；中文按相邻二元组切分。
2. 统计每条**有年份**记录的出现情况（同一记录同一词只计一次）。
3. 只保留出现于 ≥2 条记录的词项，按频次降序、词项升序取前 12 个。
4. 每个词项的 `series` 为「年份 → 该年含此词的记录数」。

## 4. 生命周期与突发

| 标签 | 规则（默认参数） |
|---|---|
| `dormant` | 最后出现年 ≤ 批末 − 3，且年份跨度 ≥ 4 |
| `emerging` | 首见年 ≥ 批末 − 2，且总提及 ≥ 2，且后半段 > 前半段 |
| `growing` | 后半段 ≥ 2 × 前半段，且后半段 ≥ 2 |
| `declining` | 前半段 ≥ 2 × 后半段，且前半段 ≥ 2 |
| `stable` | 其余（活动分散、无明确位移） |

- 前半段/后半段以 `(首年 + 末年) / 2` 为界。
- `bursts`：某年计数 > 年均值 + 标准差，且 ≥ 2。
- 每个标签都写 `basis`，说明触发的是哪条规则与哪组计数。

## 5. 主题归并、阶段映射与共现

- `stage`：`emerging → appear`、`growing → grow`、`stable → stable`、`declining → decline`、`dormant → dormant`。
- 主题归并优先级：输入 `concept_rules`（或其别名键，或 `task.md` 中的 JSON 代码块）→ `assets/theme-lexicon.json` 回退 → 词项级。每行给出 `merge_rule{rule,source}`、`merge_basis` 与 `merge_evidence[]`（词项、提及数、首末年）。
- `merge_split` 固定为 `not_detectable_from_term_counts`，并在 `merge_split_note` 说明原因。
- 共现：对每个词项对，统计同时含两词的**有年份**记录，并按前半段/后半段拆分：
  - 只在后半段出现（≥2 条）→ `candidate_merge`
  - 只在前半段出现（≥2 条）→ `candidate_split`
  - 两段都有 → `persistent_cooccurrence`
- 候选优先于持续性共现保留，最多 8 对；`conflicts` 中最多列 2 条合并候选 + 2 条分裂候选（上限 3 条）。

## 6. 阶段划分与代表工作

- 阶段划分：优先用 `case.json` 的 `periods`/`period_plan`/`stages`/`time_slices`/`year_bins`/`period_bins`（或 `task.md` 中带「阶段/period」且含两个年份范围的行）；否则把有年份窗口按 `span // 3` 等宽分箱，最多 4 段。口径写入 `method.period_rule`、`method.period_basis`，每段 `basis` 说明成立依据。
- 每段记录数、代表工作（最多 3 篇）按「批内引用数降序 → 年份 → `source_id`」选出，每段恰好一条代表。
- `representative_selection` 记录规则、`period_from`/`period_to`、该区间出现过的生命周期阶段，以及已知遗漏（无年份记录、仅提及一次的词项）。
- 引用数缺失时，所有记录按年份与 `source_id` 排序，并在 `uncertainty.no_citation_counts` 中声明。

## 7. 开放问题

- 命中线索（`future research`、`remains unclear`、`further study`、`limited evidence`、`尚未`、`仍需`、`有待` 等）时，截取线索前后文作为 `quote`，记录 `locator` 与年份。
- 每条记录最多取首个命中线索；不推断线索之外的含义。

## 8. 空白与排除

| 空白类型 | 触发 | 排除证据 |
|---|---|---|
| `no_dated_records` | 无任何有年份记录 | 无记录可核，说明字符串 |
| `single_year_batch` | 年份跨度 = 1 | 该年首条记录 |
| `dormant_terms` | 存在 `dormant` 词项 | 该词项最后代表工作的 `locator` 与年份 |
| `thin_term_signal` | 可跟踪词项 < 3 | 前 3 条有年份记录 |
| `batch_coverage` | 恒定加入 | 批末记录，说明覆盖边界 |

`gap_exclusion[].status` 固定 `batch_bounded`，`external_check_required=true`：批内缺席不等于领域空白。

## 9. 结论与证据

- `claim_evidence` 分四类：`trend`（年度分布、前后半段方向）、`evolution`（每个 emerging/growing/declining/dormant 词项一条）、`representative`（每个时间段一条）、`gap`（开放问题线索与空白）。
- 每条 claim 带 `source_ids`、`locator`、`quote`、`quote_verified`、`period`。
- `synthesis.direction`：`expanding`（仅扩张）/ `contracting`（仅收缩）/ `mixed`（两者都有）/ `flat_or_unresolved`（都不明显）/ `undetermined`（无主题、无记录或单年批）。
- `synthesis.narrative` 追加分阶段小结、批内空白与边界；`review_report` 另给四段中文叙事（时间趋势、主题演化、代表性工作、研究空白与边界）。

## 9b. 检索式与可复算表

- `retrieval_scope` 声明 `queries[]`（布尔串、字段、日期范围、语言、命中数）与 `hits_per_query[]`；命中数只在给定批次上去重后计数，`executed_online=false`，不联网。
- `render_stats()` 写 `trend_stats.json`（`year_histogram`、`period_counts`、逐条 `year/venue/citations/period/decision`、`theme_series`）与 `screening_log.csv`（每条题录一行，含 `decision`、`duplicate_of`、`locator`）。
- `report.md`、`trend_stats.json`、`screening_log.csv` 均在 `os.path.exists` 自检通过后登记到 `artifacts`。
- `self_check[]` 校验 flow 闭合、`year_counts` 升序且求和等于 `dated`、引用逐字命中、代表年份落在所属阶段；总判定写入 `validator_verdict`。

## 10. 状态判定

| `status` | 条件 |
|---|---|
| `insufficient_input` | 无主题或无记录 |
| `partial` | 有记录，但有年份记录 <2 或年份跨度 =1 |
| `success` | 主题存在，且有年份记录 ≥2 且跨 ≥2 年 |
| `failed` | case 损坏或运行异常；仍写完整契约键并 exit 0 |

## 11. 契约投影

1. 顶层已有同名字段 → 直接使用。
2. `result` 内有同名字段 → 提升到顶层。
3. 已知别名（`summary`→`synthesis`、`themes`→`theme_evolution`、`claims`→`claim_evidence`、`gaps`→`research_gaps`、`timeline`→`periods` 等）→ 用真实结果填充并记录。
4. 其余 → `not_determinable` 对象（`field`、`reason`、`closest_produced_fields`、`next_action`）。

## 12. 确定性

无随机数、无时间戳、无网络、无环境相关排序；记录按输入顺序，词项对与代表工作按显式键排序，重复运行字节级一致。
