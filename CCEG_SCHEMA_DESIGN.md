# CCEG v1/v2 Schema 设计说明

> CCEG：Contrastive Clinical Evidence Graph，对比临床证据图。  
> 状态：v1 保持冻结；v2 已冻结一元证据、确定性合成和 research-only 审核契约。  
> 适用范围：TALP P5+v2 后续 `p5kg_*` 评测，不接入生产默认路径。

## 1. 设计目标

CCEG 不构建通用“疾病—症状共现图”，而是保存可审计的临床证据 claim：

```text
(候选病 A, 候选病 B, finding@value/context)
  → supports / argues_against / common / recommends_test
  → 精确原文与来源
```

v1 schema 解决四个已知问题：

1. **association 不等于 discrimination**：方向 claim 必须绑定候选病对，而不是只声明
   “疾病 A 可见 finding F”。
2. **值和否定决定方向**：同一检查的 elevated、suppressed、normal、absent 可以指向相反结论。
3. **case report 清单不能提供方向**：来源权限由可执行 validator 强制，而非依赖 prompt 自律。
4. **错误结构化会稳定注入错误**：claim 在进入索引前必须经过 schema、来源权限、语义蕴含和
   人工审核。

## 2. 已落地文件

- Python 权威契约：
  `src/agentclinic_tree_dx/knowledge/cceg_schema.py`
- 可移植 JSON Schema：
  `data/eval/cceg_claim_schema_v1.json`
- v2 可移植 JSON Schema：
  `data/eval/cceg_claim_schema_v2.json`
- JSON/JSONL 批量审计：
  `scripts/audit_cceg_claims.py`
- 正反例测试：
  `tests/test_cceg_schema.py`

Python 模块是 schema 的单一事实源；v1 JSON Schema 由
`claim_json_schema()`（等价于 `claim_json_schema(1)`）生成，v2 由
`claim_json_schema(2)` 生成，不应手工独立演化。

## 3. 为什么采用 reified claim

普通三元组：

```text
hyperparathyroidism --has_finding--> elevated_PTH
```

不能完整表达：

- 与哪个竞争诊断比较；
- suppressed PTH 是否产生相反方向；
- finding 是否被否定；
- 适用的年龄、阶段、时间和标本；
- 证据来自哪一段原文；
- 该关系是明确鉴别、限定陈述还是病例个案；
- 是否通过自动蕴含与临床审核。

因此 CCEG 把关系本身表示为 claim 对象，并将 provenance、比较对象和质量状态作为一等字段。

## 4. 顶层结构

每条 JSONL 记录表示一个 claim，顶层字段如下。

### 4.1 身份与版本

- `schema_version`：历史 claim 固定为 `1`；新的一元/合成 claim 使用 `2`。
- `claim_id`：格式为 `cceg_<12–64 位小写十六进制>`。
- `claim_type`：
  - `direction`
  - `common`
  - `membership`
  - `phenotype_assertion`
  - `test_recommendation`
- `claim_status`：
  - `raw`
  - `pending_review`
  - `grounded`
  - `rejected`

建议抽取器根据规范化 claim 内容、来源 chunk 和 schema version 生成稳定 SHA-256，并截取
12–64 位形成 `claim_id`。当前 schema 约束格式，不负责生成算法。

### 4.2 候选实体

- `candidate_a`：必填。
- `candidate_b`：病对 claim 必填，membership/phenotype assertion 可为 `null`。
- 每个候选包含：
  - `name`
  - `id`
  - `id_provenance`
  - `l1_parent`

如果设置了标准 ID，必须同时提供 ID 来源。无法可靠映射时允许 `id=null`，不得制造 MONDO、
SNOMED 或其他伪 ID。

### 4.3 Finding

`finding` 保存：

- `surface`：原始临床表述；
- `event_type`：phenotype、laboratory、imaging、culture 等；
- `concepts[]`：HPO、LOINC、SNOMED、RadLex 等标准概念；
- `polarity`：`1`、`0` 或 `-1`；
- `value_state`：
  - `elevated`
  - `suppressed`
  - `present`
  - `absent`
  - `normal`
  - `unknown`
- `value`、`unit`、`specimen`；
- `temporal`：onset、duration、relation、anchor；
- `context`：年龄、阶段、治疗等扩展条件；
- `abstained`：术语映射是否保守弃权。

约束：

- `concepts=[]` 时必须 `abstained=true`；
- 有标准概念时不得同时 `abstained=true`；
- `extraction.normalization_abstained` 必须与 finding 状态一致。

这保证“没有概念映射”只表示 abstention，不会被误读成“没有临床证据”。

### 4.4 Relation

relation 与 claim type 一一受限：

- `direction`
  - `supports_a`
  - `supports_b`
  - `argues_against_a`
  - `argues_against_b`
- `common`
  - `common`
- `membership`
  - `member_of`
- `phenotype_assertion`
  - `typical_for`
  - `atypical_for`
- `test_recommendation`
  - `recommends_test`

任意跨类型组合都会被 Python validator 拒绝。

### 4.5 Comparator

病对作用域的 claim 必须满足：

- `candidate_b` 存在；
- `comparator.required=true`；
- `has_support_excerpt=true`；
- `has_contrast_excerpt=true`；
- `contrast_candidates` 非空。

这条约束用于阻止单病 association 被升级为鉴别关系。

membership 与 phenotype assertion 不要求 comparator，不应伪造对照证据。

### 4.6 Provenance

每条 claim 必须保存：

- `source_id`
- `chunk_id`
- `article_id`
- `section`
- `chunk_type`
- `quote`
- `quote_span: [start, end]`
- `url`
- `evidence_grade`

v1 结构 validator 要求：

- quote 非空；
- span 满足 `0 <= start < end`；
- `end - start == len(quote)`。

当前 schema **尚不读取语料索引验证 quote 是否确实等于 chunk 对应子串**；该跨文件 hydration
检查属于后续 L1 provenance validator，必须在 KG 抽取阶段补充，不能把当前结构通过误认为
原文已经接地。

### 4.7 Extraction

`extraction` 包含：

- `pipeline`
- `model`
- `prompt_sha256`
- `confidence`
- `entailment_status`
  - `unvalidated`
  - `grounded`
  - `rejected`
  - `conflict`
- `normalization_abstained`
- `normalization_reason`

prompt 使用 SHA-256 固定，使抽取批次可以复现并纳入后续 p5kg cache signature。

### 4.8 Audit 与 Review

`audit`：

- `enumeration_only`
- `pair_binding_ok`
- `negation_scope_ok`
- `value_scope_ok`

`review`：

- `status`：`unreviewed|accepted|rejected`
- `reviewer_ids`
- `adjudication`

`grounded` claim 的额外要求：

- entailment 必须为 `grounded`；
- review 必须为 `accepted`；
- direction/common/test claim 至少有 2 个不同 reviewer；
- membership/phenotype claim 至少有 1 个 reviewer；
- pair binding、negation scope、value scope 均通过；
- 病对 claim 不得是 enumeration-only。

case-report 清单可以作为经过审核的 membership claim，因此 membership 的
`enumeration_only=true` 是合法状态；它仍不能成为方向 claim。

### 4.9 Split

每条 claim 必须记录：

- `document_family`
- `document_split`：`build|audit|held_out`
- `family_held_out`
- `pilot_scope`

这些字段用于：

- 保证同一 source/article 不跨构建与审核集合；
- 支持 family-held-out；
- 防止在看过端到端结果后无记录地修改抽取规则。

## 5. 来源权限

### 5.1 CPG prose

`source_class=cpg_prose` 可以产生：

- direction
- common
- membership
- phenotype assertion
- test recommendation

方向性 claim 仍需完整 comparator、原文和双人审核。

### 5.2 CPG enumeration

`source_class=cpg_enumeration` 只能产生 membership。

“Differential diagnosis includes A, B, C” 只能说明候选属于比较集，不能说明某个 finding
支持或反对其中任一疾病。

### 5.3 Case-report list

`source_class=case_report_list` 只能产生 membership，且：

- `strength=anecdotal`；
- 可标 `enumeration_only=true`；
- 不得进入方向 consumer。

### 5.4 Case-report prose

`source_class=case_report_prose` 可以产生：

- membership；
- phenotype assertion。

强度必须为 anecdotal。即使病例确诊，也不能把个案表现自动提升为群体 LR 或候选病对方向边。

### 5.5 Oracle

`source_class=oracle` 可表达所有 claim type，但只用于 G5 理论上界。Oracle 文件必须与自动抽取
产物分离，并拥有独立 manifest。

## 6. Consumer 权限

v1 只允许以下 consumer 标签：

- `audit`
- `p3_soft`
- `p4_soft`
- `p5_soft`
- `p5_veto`

schema 不提供 `hard_direction` 或类似权限。即使 claim 已 grounded，首轮实验仍只能作为
P5 的软先验；是否晋级必须由 G0–G6 配对实验决定。

## 7. Claim 生命周期

```text
raw
 │
 ├─ L0 schema/source-policy 失败 ──────────────> rejected
 │
 └─ L0 通过
      │
      ├─ L1 provenance/entailment 冲突 ───────> rejected
      ├─ L1 尚不确定 ─────────────────────────> pending_review
      └─ L1 通过
           │
           ├─ 人工拒绝 ───────────────────────> rejected
           └─ 人工接受 + reviewer 门满足 ─────> grounded
```

只有 `grounded` claim 才能进入 validated index。`raw` 和 `pending_review` 只能进入审计队列。

当前已实现：

- L0 字段和跨字段语义；
- 来源权限；
- review 数量门；
- batch duplicate ID 检测。

后续抽取阶段仍需实现：

- quote 对 corpus metadata 的真实 hydration 校验；
- 独立 entailment validator；
- 自动否定/value comparator 探针；
- 人工审核包与 κ/precision 统计；
- validated/oracle 索引构建。

## 8. JSON Schema 与 Python Validator 的职责

### JSON Schema

适合：

- 必填字段；
- 类型、枚举和格式；
- 允许的嵌套结构；
- 阻止未知字段。

### Python Validator

额外执行：

- claim type 与 relation 一致性；
- source class 权限；
- 病对/comparator 完整性；
- ID 与 ID provenance 一致性；
- concepts 与 abstention 一致性；
- case report 强度；
- grounded 状态、entailment 和 reviewer 数量；
- quote/span 长度；
- allowed consumer 白名单。

因此，只通过通用 JSON Schema validator 不代表 claim 可以入库；必须同时通过
`cceg_schema.validate_claim()`。

## 9. 使用方式

### 9.1 导出 schema

```bash
PYTHONPATH=src python scripts/audit_cceg_claims.py \
  --schema-out data/eval/cceg_claim_schema_v1.json
```

导出器默认拒绝覆盖已有文件。若 schema 需要改变，应升级版本，而不是静默覆盖 v1。

### 9.2 审计 JSONL

```bash
PYTHONPATH=src python scripts/audit_cceg_claims.py \
  data/cceg/pilot/claims.raw.jsonl \
  --report logs/cceg_eval/schema_audit.json
```

返回码：

- `0`：所有 claim 通过；
- `1`：至少一条 claim 无效；
- 参数/JSON 错误：非零退出。

batch report 包含：

- claim 总数；
- valid/invalid 数量；
- claim type/source/status 分布；
- duplicate IDs；
- 每条无效 claim 的完整错误列表；
- `publishable`。

空批次不会被标为 publishable。

### 9.3 Python API

```python
from agentclinic_tree_dx.knowledge.cceg_schema import (
    CCEGValidationError,
    assert_valid_claim,
    validate_claim,
)

errors = validate_claim(payload)
if errors:
    ...

try:
    assert_valid_claim(payload)
except CCEGValidationError as exc:
    print(exc.errors)
```

## 10. 正反例语义

测试已覆盖：

1. CPG grounded direction claim；
2. case-report list 生成 direction 时拒绝；
3. case-report enumeration 作为 membership 时允许；
4. 病对缺失 candidate B/contrast/reviewer 时拒绝；
5. 未映射 finding 必须显式 abstain；
6. quote/span 不一致时拒绝；
7. batch claim ID 重复时拒绝；
8. v1/v2 导出的 JSON Schema 必须与 Python 权威契约一致；
9. synthetic candidate effect 只能进入 research P3/P4；
10. association 必须 audit-only，unary claim 不得绕过 composition 进入 P5；
11. synthetic review 不得冒充 human grounded；
12. candidate effect 的 CPG enumeration/case-report 来源必须拒绝；
13. derived contrast 必须具有双 chunk provenance 和完整 derivation；
14. derived contrast 只能使用 composed 来源并进入对应 P5 consumer。

执行：

```bash
PYTHONPATH=src python -m pytest \
  tests/test_cceg_schema.py -q
```

当前 schema 专项结果：18 passed。

## 11. 版本治理

任何以下变化都应升级 `schema_version`：

- relation/claim type 语义改变；
- 来源权限改变；
- grounded 放行条件改变；
- 必填 provenance 改变；
- comparator 语义改变；
- consumer 权限改变。

升级步骤：

1. 新增 v2 Python schema/迁移逻辑；
2. 导出独立 JSON Schema 文件；
3. 保留 v1，不原地覆盖历史 schema；
4. 更新抽取 prompt hash；
5. 更新 CCEG asset manifest；
6. 将 schema version、claim 文件 SHA、prompt SHA 纳入 P5 compiler cache signature；
7. 重新运行构图质量门和 G0–G6，不跨版本直接合并结果。

## 12. v2 一元证据与派生证据

v2 是与 v1 并存的独立契约。`validate_claim()` 按记录自身的
`schema_version` 分派；不迁移、不补写、也不改变 v1 记录。无参
`claim_json_schema()` 继续返回 v1，以免既有导出器和审计任务静默切换版本。

### 12.1 `candidate_effect`

`candidate_effect` 表达单个候选与单个 finding-state 的直接原文关系：

- `candidate_b=null`；
- `relation` 只能是
  `supports_candidate|argues_against_candidate|associated_with`；
- `comparator.required=false`、`has_contrast_excerpt=false` 且
  `contrast_candidates=[]`；
- `provenance` 必须是单条完整原文来源；
- `provenance_bundle=[]`、`derivation=null`；
- 只允许 `cpg_prose` 或隔离的 `oracle` 来源。CPG enumeration、case-report list
  和 case-report prose 均不得生成该方向结构。

`associated_with` 只证明关联，必须保持 `allowed_consumers=["audit"]`，不能参加方向合成。
其余 `candidate_effect` 即使通过审核，也不能取得
`p5_soft|p5_veto|research_p5_soft`；进入 P5 前必须先通过白名单 composer 生成
`derived_contrast`。

### 12.2 `derived_contrast`

`derived_contrast` 不是抽取结果，只能是确定性 composition 产物：

- `source_class="composed"`，其他 claim type 不得使用该来源类；
- `candidate_a`、`candidate_b` 和完整 comparator 均必填；
- 顶层 `provenance=null`，禁止把多前提派生边伪装成一条 source quote；
- `provenance_bundle` 至少包含两条完整 provenance，覆盖至少两个不同 chunk；
- `derivation.derived=true`；
- `derivation.premise_claim_ids` 至少两个、格式合法且互不重复；
- `derivation.composition_rule` 非空；
- `extraction.pipeline="deterministic_composition"`，LLM direct extraction 必须拒绝；
- provenance 数量必须与 premise claim 数量相同。

研究轨派生 claim 只允许 `audit|research_p5_soft`，人工轨派生 claim 只允许
`audit|p5_soft`。因此 unary 证据不能绕过 composer 直接进入 P5，合成证据也不能回流
P3/P4 或取得 veto 权限。

### 12.3 synthetic dual-LLM review

v2 `review` 新增：

```json
{
  "mode": "synthetic_dual_llm",
  "status": "accepted",
  "reviewer_ids": ["reviewer-a", "reviewer-b"],
  "reviewer_runs": [
    {
      "reviewer_id": "reviewer-a",
      "model": "model-a",
      "prompt": "frozen reviewer prompt a",
      "prompt_sha256": "<64 lowercase hex>",
      "seed": 11
    },
    {
      "reviewer_id": "reviewer-b",
      "model": "model-b",
      "prompt": "frozen reviewer prompt b",
      "prompt_sha256": "<64 lowercase hex>",
      "seed": 29
    }
  ],
  "adjudication": "reviewers agreed"
}
```

每个 reviewer run 都必须冻结 reviewer ID、model、prompt、prompt SHA-256 和非负 seed；
`synthetic_dual_llm` 至少需要两个不同 reviewer，且两条 model/prompt/seed 配置不得完全相同。
若后续 reviewer 不一致，
`adjudication` 保存独立裁决结论，裁决调用的冻结信息应作为额外 reviewer run 保存。

synthetic 结果必须同时满足：

- `claim_status="research_validated"`；
- `extraction.entailment_status="grounded"`；
- `review.status="accepted"`；
- pair binding、negation scope、value scope audit 均通过；
- 不得取得除 `audit` 外的任何 v1 临床 consumer；
- research consumer 只能用于
  `research_p3_soft|research_p4_soft|research_p5_soft` 中与 claim type 相符的阶段。

反向约束同样成立：`research_validated` 和任意 research consumer 都要求
`review.mode="synthetic_dual_llm"`。它不能被表示成 `grounded`、human-signed 或
clinical-grade，只能用于离线 A/B 研究。

### 12.4 v2 来源和 consumer 权限

v1 的来源权限保持不变。v2 只增加两项权限：

1. `cpg_prose`（以及隔离 oracle）可产生 `candidate_effect`；
2. `composed` 只可产生 `derived_contrast`。

`candidate_effect` 的研究 consumer 上限为 `research_p3_soft|research_p4_soft`；
`derived_contrast` 的研究 consumer 只能是 `research_p5_soft`。`associated_with`
始终 audit-only。所有权限均由 Python validator 执行，JSON Schema 只负责字段形状和枚举。

### 12.5 v2 导出

```bash
PYTHONPATH=src python -c \
  'import json; from pathlib import Path; from agentclinic_tree_dx.knowledge.cceg_schema import claim_json_schema; Path("data/eval/cceg_claim_schema_v2.json").write_text(json.dumps(claim_json_schema(2), ensure_ascii=False, indent=2) + "\n")'
```

`data/eval/cceg_claim_schema_v1.json` 不得覆盖。两个导出文件都由测试逐对象比对 Python
权威契约。

## 13. 与后续实验的关系

schema 是抽取前置合同，不代表 GraphRAG 已经实现。

后续顺序必须是：

1. 冻结 pilot families、document/source split 和 query scope；
2. 依据 v1 schema 抽取 raw claims；
3. 执行 L0/L1/人工质量门；
4. 生成 validated claims；
5. 先运行 G1、G2、G5，判断结构化 claim 是否存在有效上界；
6. 只有 G2/G5 证明存在 headroom，才构建 G3/G4 图遍历；
7. G6 的 case-report membership 单独评估，不与 CPG direction 混合归因。

如果 G5 oracle 不能无回归地超过 G0，应停止扩图，转向 consumer 软路由、grounded LR 和
fixture 治理。
