---
name: research-trend-and-theme-evolution
description: Use when a dated batch of papers must be turned into a defensible research-frontier picture — yearly output, per-term activity series with lifecycle labels, burst years, representative work per period, theme appearance/growth/decline, open questions and batch-bounded gaps, each claim tied to a locator and an exact quote. Runs offline with the Python standard library only.
---

# 研究前沿与主题演化分析

## 用途

把一个主题和一批**带年份**的文献记录，转成可复核的趋势判断，交付六类相互一致的内容：

1. **时间分布**：逐年文献量、年份跨度、峰值年，明确「绝对值、未按数据库规模归一」。
2. **主题词演化**：高频词项的逐年序列、生命周期标签（`emerging` / `growing` / `stable` / `declining` / `dormant`）及判定依据；映射到 `appear` / `grow` / `stable` / `decline` / `dormant` 阶段。
3. **阶段拐点**：`bursts`（逐年计数高于均值+标准差且 ≥2）标出突发年份。
4. **代表工作**：按时间段选代表（批内引用数最高，平票按年份、`source_id`），并说明选择规则与已知遗漏。
5. **未解决问题与空白**：只收录摘要中**明确写出**的开放问题线索，以及本批内的信号空白（休眠词项、单年批、词项过少、批覆盖边界）。
6. **结论与证据**：每条趋势、演化、代表与空白结论都带 `locator`、`quote`、`period`、`source_ids`；综合结论说明方向与边界，不做预测。

合并/分裂只作为**共现候选**报告：同一对词项若只在时间窗后半段共现，标 `candidate_merge`；只在前半段共现，标 `candidate_split`。明确标注这是候选而非确认。

## 适用条件

- 输入含主题（`topic` / `research_topic` / `question` / `field` / `domain` / `objective` 之一，或 `task.md` 首行）与文献记录。
- 记录位于 `records` / `papers` / `documents` / `literature` / `sources` / `items`，也可嵌套在更深对象中。
- 至少 2 条带年份记录、跨 ≥2 个年份时给出 `success`；否则如实降级。
- 需要「这几年这个方向怎么变、哪些主题在起、哪些在落、代表工作是谁、证据在哪里」，而非预测或引文网络分析。

## 不适用

- 预测未来发文量、引用量或技术成熟度。
- 需要外部数据库检索、引文网络、共被引/耦合分析或主题模型（LDA/BERTopic）。
- 用词频替代专家判断来确认「合并/分裂」「范式转移」或「领域空白」。
- 输入只有无年份记录却要求趋势结论。
- 需要对单篇论文做方法学质量评价。

## 输入形态

```text
<input>/
  case.json        # 必需；缺失时按空输入处理，仍 exit 0
  task.md          # 可选；无 topic 时取第一条正文行作为主题
  <其他材料>        # 只登记到 input_manifest（路径、字节、sha256 前 1MB），不参与统计
```

`case.json` 关键字段：

| 字段 | 说明 |
|---|---|
| `case_id` | 原样回写；缺失时为 `unknown` |
| `topic` 等 | 主题文本；缺失时由 `task.md` 兜底 |
| 记录数组 | 每条含 `title`、`abstract`、`year`、`citations`、`doi`、`venue` |
| `output_contract` | 对象、字段名列表或 JSON Schema（含 `properties`）均可 |

年份支持整数或文本中的四位年份（1800–2100）；无法解析视为无年份，并在 `uncertainty`、`needs_human_confirmation` 中标注。

## 调用方式

```bash
python3 /skills/weekly-skill/scripts/sk_entry.py --input /input --work /app/work --out /app/output
```

等价薄封装：

```bash
python3 /skills/weekly-skill/scripts/run_skill.py --input /input --work /app/work --out /app/output
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--input` | `/input` | 输入目录或 `case.json`；兼容旧名 `--case` |
| `--work` | `/app/work` | 工作目录；主输出不可写时回退到此 |
| `--out` | `/app/output` | 目录（写 `result.json`）或 `.json` 文件；兼容旧名 `--output` |

仅标准库、不联网、无随机与时间依赖。**任何情况下退出码为 0** 并总是尝试写 `result.json`。

## 输出契约

顶层固定字段：`case_id`、`status`（`success` / `partial` / `insufficient_input` / `failed`）、`result`、`evidence[]`、`uncertainty[]`、`errors[]`、`stats`、`input_manifest[]`、`run`、`contract_notes`、`contract_extras`、`output_contract_fields`。

`result` 内固定字段：

| 字段 | 内容 |
|---|---|
| `trend_overview` | `records`、`dated_records`、`year_range`、`year_counts`、`peak_year`、`growth_note` |
| `terms[]` | `term`、`mentions`、`first_year`、`last_year`、`series`、`lifecycle`、`basis`、`bursts[]`、`representative[]` |
| `theme_evolution[]` | `theme`、`stage`、`lifecycle_label`、`from_year`、`to_year`、`series`、`basis`、`source_ids`、`merge_split`、`merge_split_note` |
| `cooccurrence[]` | 词项对、`records`、`early_half`、`late_half`、`label`（`candidate_merge` / `candidate_split` / `persistent_cooccurrence` / `none_detected`） |
| `claim_evidence[]` | `category`（`trend` / `evolution` / `representative` / `gap`）、`claim`、`source_ids`、`locator`、`quote`、`quote_verified`、`period` |
| `periods[]` | 时间段、记录数、代表工作、选择规则 |
| `representative_selection[]` | 时间段、规则、`covered_stages`、`known_omissions` |
| `open_questions[]` | 明确写出的开放问题线索、`locator`、`quote`、年份 |
| `conflicts[]` | 生命周期背离，以及共现候选的合并/分裂 |
| `research_gaps[]` | `type` + `basis`，只写批内空白 |
| `evidence_matrix[]` | 每条记录的来源、年份、比较字段、是否进入序列、纳排理由、`locator`、`quote` |
| `gap_exclusion[]` | `gap`、`basis`、`search_scope`、`exclusion_evidence[]`、`status`、`external_check_required` |
| `needs_human_confirmation[]` | `item`、`locator`、`reason` |
| `synthesis` | `narrative`、`direction`、`strongest_signals`、`caveats`、`bounded_by`、`not_a_forecast`、`decision_scope` |
| `retrieval_scope` | `query`、`inclusion`、`exclusion`、`batch_size`、`dated_batch_size`、`year_range`、`screened_out`、`external_search` |
| `method` / `limitations` / `change_log` | 规则、限制、处理步骤 |

`output_contract` 处理规则：

1. 每个契约键都出现在**顶层**；同名业务字段直接复用，`result` 内的同名同义字段提升到顶层。
2. 认识的别名（如 `report`/`summary` → `synthesis`、`themes` → `theme_evolution`、`claims` → `claim_evidence`、`gaps` → `research_gaps`、`timeline`/`representative_works` → `periods`、`notes` → `uncertainty`）按真实结果填充，记入 `contract_extras.aliases_applied`。
3. 无法映射的键写结构化「无法判断」对象（`status=not_determinable`、`field`、`reason`、`closest_produced_fields`、`next_action`），不留 `null`、不留空容器，并记入 `contract_extras.not_determinable_keys`。

## 处理流程

1. **读入与盘点**：解析 `case.json`；登记输入清单；区分有年份与无年份记录，写入 `retrieval_scope`。
2. **年度分布**：统计逐年计数、年份范围、峰值年；比较前后半段计数给出方向。
3. **词项序列**：英文词（≥3 字符、去停用词）+ 中文二元组；只保留在 ≥2 条有年份记录中出现的词项，最多 12 个。
4. **生命周期**：按首末出现年、前后半段计数、最近 3 年是否出现判定；每项给出可读 `basis`。
5. **突发年**：逐年计数 > 均值 + 标准差且 ≥2 的年份进入 `bursts`。
6. **代表工作与阶段**：按三等分年份区间选代表；将生命周期映射到演化阶段；对每对词项计算前后半段共现，给出合并/分裂候选。
7. **证据与结论**：为趋势、演化、代表、空白各生成 `claim_evidence`；空白另做排除检查（`gap_exclusion`）；汇总 `synthesis`（`expanding` / `contracting` / `mixed` / `flat_or_unresolved` / `undetermined`）并声明不预测。

阈值与上限由 `assets/policy.json` 提供（休眠窗口、增长倍数、词项数、引文长度、清单上限），脚本缺省值与之相同。

## 证据要求

- `evidence` 每条含 `source_id`、`locator`（如 `/records/2`）、`quote`；`quote` 为所引字段的**精确子串**，超长截取前缀并置 `truncated=true`，`quote_verified` 记录校验结果。
- `claim_evidence` 每条至少给出一个 `locator` 与 `quote`；`source_ids` 必须能在输入记录中找到。
- 代表工作必须说明「批内引用」而非领域引用；无引用计数时说明改用年份与 `source_id` 排序。
- 没有来源的推断（合并/分裂确认、领域空白、机制解释）只能写进 `needs_human_confirmation`。
- 不编造记录、年份、期刊、引用数或开放问题原文；不把批内缺席写成领域空白。

## 异常处理

| 情形 | 处理 | 标记 |
|---|---|---|
| `case.json` 缺失 | 空输入分析，仍写 `result.json`、exit 0 | `status=insufficient_input`，`errors[].type=case_file_missing` |
| `case.json` 损坏或非对象 | 结构化失败结果，仍 exit 0 | `status=failed`，`errors[].type=case_unreadable` |
| 无主题 | 不做方向判断 | `status=insufficient_input`，`uncertainty.type=no_topic` |
| 无记录 | 不做任何趋势结论 | `status=insufficient_input`，`uncertainty.type=no_records` |
| 有年份记录 <2 或年份跨度 =1 | 只给计数，不给趋势 | `status=partial`，`research_gaps.type=single_year_batch` |
| 记录无年份 | 排除出序列，保留开放问题提取 | `uncertainty.type=undated_records`、`needs_human_confirmation` |
| 词项不足 3 个 | 明确信号过薄 | `research_gaps.type=thin_term_signal` |
| 引用数为零 | 代表工作退化为按年份/编号 | `uncertainty.type=no_citation_counts` |
| 共现出现新组合 | 只报候选 | `conflicts[].type=candidate_merge/candidate_split` |
| 输出目录不可写 | 回退到 `--work`；再失败只写 stderr | 退出码仍为 0 |
| 未知契约键 | 结构化 `not_determinable` + `contract_extras` | 顶层键不缺 |

## 限制

- 词项序列依赖标题/摘要措辞，无法识别同义改写、缩写与跨语言表达。
- 合并/分裂只能给共现候选，不能确认；需要更长窗口与外部索引。
- 引用数若提供，仅为批内计数，未做领域归一。
- 生命周期是启发式阈值，摘要收录延迟会伪造「新兴」或「休眠」。
- 不做预测、主题模型、引文网络或数据库规模归一。
- 除 case 记录外不解析其他材料文件，也不访问网络。

## 最小示例（示例，非正式案例结果）

```bash
python3 scripts/sk_entry.py --input examples/demo-case --work /tmp/demo-work --out /tmp/demo-out
```

演示输入为**合成数据**（`examples/demo-case/case.json`）：8 条记录（7 条有年份、跨度 2019–2025、1 条无年份）、10 个 `output_contract` 键。预期：

- `status=success`，`case_id=demo-trend-001`；
- `terms` 10 项，含 `crispr`（growing）、`persistence`（declining）、`machine`（emerging）、`cohort` 与 `cytokine`（dormant）；
- `conflicts` 至少含 `diverging_term_lifecycles` 与一条 `candidate_merge` / `candidate_split`；
- `synthesis.direction=mixed`，明确 `not_a_forecast=true`；
- 10 个契约键全部位于顶层，`not_determinable` 为空；
- `evidence` 的 `quote_verified` 全部为 `true`，无年份记录出现在 `needs_human_confirmation`。

示意输出（截断）：

```json
{"status": "success", "case_id": "demo-trend-001",
 "result": {"synthesis": {"direction": "mixed", "not_a_forecast": true},
            "conflicts": [{"type": "candidate_merge"}]}}
```

完整数值以实际运行为准；示例不代表任何平台固定案例结果。运行说明见 `examples/quickstart.md`。

## 交付自检

- [ ] `python3 scripts/sk_entry.py --input <案例目录> --work <临时目录> --out <临时目录>` 退出码 0，`result.json` 存在。
- [ ] `case_id` 与输入一致；`status` 只取四个枚举，且与 `uncertainty`、`research_gaps` 自洽。
- [ ] `output_contract` 每个键都在顶层，无 `null`/`TODO`；无法产出者带 `status=not_determinable` 与原因。
- [ ] 六个交付面（年度分布、词项演化、代表工作、开放问题、空白、证据）都有实质内容。
- [ ] 每条 `claim_evidence` 的 `quote` 能在 `locator` 指向字段逐字找到（`quote_verified=true`）。
- [ ] 合并/分裂只以候选形式出现，措辞未升级为确认。
- [ ] 无年份记录未被静默丢弃：出现在 `uncertainty` 或 `needs_human_confirmation`。
- [ ] 重复运行两次，`result.json` 内容一致；无 `__pycache__`、无令牌或密钥。
- [ ] 保留 `GITHUB_URL.txt` 原样，文件数与总大小在 50 个 / 2MB 以内。
