# 题面要求 → 实现落点（`challenge-073af7d3`）

本文件把 `03_brief/statement.md` 的要求逐条映射到包内可运行的部分，便于评审按条复核；不是评分自述，也不代表平台分数。

## 1. 四类可检查产物（题面「实际效果」主线）

| 题面要求 | 实现位置 | 检查方式 |
|---|---|---|
| 时间趋势由可核对的年度分布支撑 | `result.trend_overview`（`year_counts`、`year_range`、`peak_year`）+ `result.claim_evidence[category=trend]` | 逐年计数可对输入记录复算；峰值年与计数一致 |
| 主题演化说清「什么时候、因为什么变化」 | `result.theme_evolution[]`（`stage`、`from_year`、`to_year`、`series`、`basis`）+ `result.terms[]` | 每个阶段都能看到前后半段计数与首末出现年 |
| 代表作覆盖各阶段且口径可说明 | `result.periods[]` + `result.representative_selection[]` | 规则写明「批内引用最高，平票按年份与 `source_id`」；`known_omissions` 说明遗漏 |
| 研究空白有排除证据而非检索遗漏 | `result.research_gaps[]` + `result.gap_exclusion[]` + `result.retrieval_scope` | 每条空白带 `search_scope` 与 `exclusion_evidence`，并标 `batch_bounded` |

## 2. 六类题集内容

| 题面内容 | 字段 |
|---|---|
| 问题拆解 | `retrieval_scope.query`、`query_basis`、`result.synthesis` 的边界声明 |
| 检索覆盖 | `retrieval_scope`（`inclusion`、`exclusion`、`batch_size`、`dated_batch_size`、`screened_out`、`external_search=false`） |
| 证据回链 | `claim_evidence[]`、`evidence[]`、`evidence_matrix[]`（`locator` + 精确 `quote`） |
| 冲突证据 | `conflicts[]`（生命周期背离 + 共现候选），`handling` 说明不裁决 |
| 综合结论 | `synthesis`（`direction`、`narrative`、`caveats`、`not_a_forecast=true`） |
| 研究空白 | `research_gaps[]` + `gap_exclusion[]` |

## 3. 题面判据（第 1 节末段）

| 题面判据 | 对应实现 |
|---|---|
| 趋势是否由可核对的年度分布支撑 | `year_counts` 与 `claim_evidence` 的 `quote` 均指向具体记录 |
| 演化是否说清时间与原因 | `theme_evolution.basis` 给出规则触发条件（首见年、前后半段倍数、休眠间隔） |
| 代表作口径 | `representative_selection.rule` 与 `known_omissions` |
| 空白是否有排除证据 | `gap_exclusion.exclusion_evidence[]`，无记录时如实返回说明字符串 |

## 4. 平台运行契约（第 3 节）

| 契约 | 实现 |
|---|---|
| 读实际文件而非标签 | 只解析 `case.json` 中的真实字段；其他输入文件只登记哈希清单 |
| `/app/output/result.json` 含全部 `output_contract` 字段与 `case_id` | 顶层写入每个契约键；缺省用结构化 `not_determinable` |
| 诚实状态、来源、不确定性、变更记录 | `status`、`evidence`、`uncertainty`、`change_log` |
| 部分结果标明限制 | `limitations`、`needs_human_confirmation`、`status=partial` |
| 不编造缺失的科研数据 | `assets/policy.json` 的 `no_fabrication` 列表 + 代码中无任何外部数据源 |

## 5. 评分维度对应（仅说明覆盖点，不声称分数）

| 维度 | 包内证据 |
|---|---|
| 实际效果 | 四类产物齐全；逐年计数可复算；空白带排除证据 |
| 使用增益 | 单入口一次运行产出统计、演化、代表作、空白与证据矩阵，省去手工补年份与重算 |
| 创新增益 | 生命周期 + 共现候选 + 代表性口径 + 空白排除的可复核组合 |
| 可靠体验 | 任意输入退出码 0、缺输入降级、契约键始终齐全、确定性输出 |
| 生态贡献 | `SKILL.md`、`references/` 三篇、`assets/policy.json`、可离线复现的 `examples/` |

## 6. 明确不做

- 不提交预制答案或正式案例结果；`examples/demo-case` 是合成演示。
- 不声称官方评分、排名或增益数据；对照由组织方生成。
- 不联网、不核实文献真实性、不做引文网络或主题模型。
- 不把合并/分裂写成已确认结论，不把批内缺席写成领域空白。
