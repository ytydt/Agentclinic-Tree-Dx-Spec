# Static Diagnosis-QA Mode Specification (Part 3)
## JSON Schemas and concrete example I/O traces

This document continues the Static Diagnosis-QA Mode Specification and should be read together with Parts 1 and 2. It provides:
- JSON Schema-style contracts for key mode-specific modules,
- canonical example payloads,
- and end-to-end example traces for both multiple-choice and open-ended diagnosis-centric QA tasks.

The goal of this document is to make the mode directly testable and implementation-ready.

---

## 24. JSON contract principles

All mode-specific module outputs must satisfy the following general rules:

1. Output must be valid JSON.
2. No free-text prose may appear outside the JSON object.
3. All enumerated fields must use one of the allowed enum values.
4. Empty strings should be used only where explicitly allowed.
5. Unknown keys should be disallowed in strict validation mode.
6. Numeric scores should be bounded where applicable.
7. Provenance fields are mandatory for all derived and interpretive evidence.

---

## 25. Shared schema fragments

### 25.1 EvidenceItem schema

```json
{
  "$id": "EvidenceItem",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "kind", "content", "source_ids", "independent", "branch_links", "metadata"],
  "properties": {
    "id": {"type": "string"},
    "kind": {"type": "string", "enum": ["direct", "derived", "interpretive"]},
    "content": {"type": "string"},
    "source_ids": {
      "type": "array",
      "items": {"type": "string"}
    },
    "independent": {"type": "boolean"},
    "branch_links": {
      "type": "object",
      "additionalProperties": {"type": "string"}
    },
    "metadata": {
      "type": "object"
    }
  }
}
```

### 25.2 BranchDecision schema

```json
{
  "$id": "BranchDecision",
  "type": "object",
  "additionalProperties": false,
  "required": ["branch_id", "decision", "rationale"],
  "properties": {
    "branch_id": {"type": "string"},
    "decision": {
      "type": "string",
      "enum": ["expand_now", "keep_coarse", "park", "close_for_now", "confirm", "reopen", "live"]
    },
    "rationale": {"type": "string"}
  }
}
```

### 25.3 CandidateAnalyticLeaf schema

```json
{
  "$id": "CandidateAnalyticLeaf",
  "type": "object",
  "additionalProperties": false,
  "required": ["leaf_id", "branch_id", "type", "content", "score", "why"],
  "properties": {
    "leaf_id": {"type": "string"},
    "branch_id": {"type": "string"},
    "type": {
      "type": "string",
      "enum": ["APPLY_DIRECT_FACT", "RUN_CALCULATOR", "QUERY_KNOWLEDGE", "TEST_OPTION_MAPPING", "CHALLENGE_LEADING_BRANCH"]
    },
    "content": {"type": "string"},
    "score": {"type": "number"},
    "why": {"type": "string"}
  }
}
```

---

## 26. Module output schemas

## 26.1 `VignetteParser` output schema

```json
{
  "$id": "VignetteParserOutput",
  "type": "object",
  "additionalProperties": false,
  "required": ["direct_evidence", "answer_options"],
  "properties": {
    "direct_evidence": {
      "type": "array",
      "items": {"$ref": "EvidenceItem"}
    },
    "answer_options": {
      "type": "array",
      "items": {"type": "string"}
    }
  }
}
```

### Example output

```json
{
  "direct_evidence": [
    {
      "id": "E1",
      "kind": "direct",
      "content": "46-year-old woman with sudden pleuritic chest pain",
      "source_ids": [],
      "independent": true,
      "branch_links": {},
      "metadata": {"span": "sentence_1"}
    },
    {
      "id": "E2",
      "kind": "direct",
      "content": "shortness of breath",
      "source_ids": [],
      "independent": true,
      "branch_links": {},
      "metadata": {"span": "sentence_1"}
    },
    {
      "id": "E3",
      "kind": "direct",
      "content": "recent long-haul flight",
      "source_ids": [],
      "independent": true,
      "branch_links": {},
      "metadata": {"span": "sentence_2"}
    }
  ],
  "answer_options": [
    "A. Pneumonia",
    "B. Pulmonary embolism",
    "C. Myocardial infarction",
    "D. Panic attack"
  ]
}
```

---

## 26.2 `RootSelector` output schema

```json
{
  "$id": "RootSelectorOutput",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "root_label",
    "time_course",
    "supporting_evidence_ids",
    "excluded_root_candidates",
    "need_external_knowledge",
    "knowledge_query_if_needed",
    "confidence"
  ],
  "properties": {
    "root_label": {"type": "string"},
    "time_course": {"type": "string"},
    "supporting_evidence_ids": {
      "type": "array",
      "items": {"type": "string"}
    },
    "excluded_root_candidates": {
      "type": "array",
      "items": {"type": "string"}
    },
    "need_external_knowledge": {"type": "boolean"},
    "knowledge_query_if_needed": {"type": "string"},
    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
  }
}
```

### Example output

```json
{
  "root_label": "acute pleuritic chest-pain syndrome with dyspnea",
  "time_course": "acute",
  "supporting_evidence_ids": ["E1", "E2", "E3"],
  "excluded_root_candidates": ["isolated chest pain", "isolated dyspnea"],
  "need_external_knowledge": false,
  "knowledge_query_if_needed": "",
  "confidence": 0.86
}
```

---

## 26.3 `BranchCreator` output schema

```json
{
  "$id": "BranchCreatorOutput",
  "type": "object",
  "additionalProperties": false,
  "required": ["branches", "frontier", "need_external_knowledge", "knowledge_query_if_needed"],
  "properties": {
    "branches": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "label", "status", "prior_estimate", "danger", "why_included"],
        "properties": {
          "id": {"type": "string"},
          "label": {"type": "string"},
          "status": {"type": "string", "enum": ["live", "parked", "other"]},
          "prior_estimate": {"type": "number", "minimum": 0.0, "maximum": 1.0},
          "danger": {"type": "number", "minimum": 0.0, "maximum": 1.0},
          "why_included": {"type": "string"}
        }
      }
    },
    "frontier": {
      "type": "array",
      "items": {"type": "string"}
    },
    "need_external_knowledge": {"type": "boolean"},
    "knowledge_query_if_needed": {"type": "string"}
  }
}
```

### Example output

```json
{
  "branches": [
    {
      "id": "B1",
      "label": "pulmonary embolism",
      "status": "live",
      "prior_estimate": 0.38,
      "danger": 0.90,
      "why_included": "acute pleuritic pain, dyspnea, and travel history fit"
    },
    {
      "id": "B2",
      "label": "infectious pleural or pulmonary cause",
      "status": "live",
      "prior_estimate": 0.24,
      "danger": 0.45,
      "why_included": "pleuritic pain may reflect pneumonia or pleuritis"
    },
    {
      "id": "B3",
      "label": "acute coronary syndrome or pericardial cause",
      "status": "parked",
      "prior_estimate": 0.16,
      "danger": 0.75,
      "why_included": "dangerous chest-pain branch retained for safety"
    },
    {
      "id": "B4",
      "label": "other",
      "status": "other",
      "prior_estimate": 0.22,
      "danger": 0.20,
      "why_included": "residual bucket"
    }
  ],
  "frontier": ["B1", "B2", "B3"],
  "need_external_knowledge": false,
  "knowledge_query_if_needed": ""
}
```

---

## 26.4 `TemporaryAnalyticLeafPlanner` output schema

```json
{
  "$id": "TemporaryAnalyticLeafPlannerOutput",
  "type": "object",
  "additionalProperties": false,
  "required": ["candidate_leaves_ranked", "selected_primary_action"],
  "properties": {
    "candidate_leaves_ranked": {
      "type": "array",
      "items": {"$ref": "CandidateAnalyticLeaf"}
    },
    "selected_primary_action": {
      "type": "object",
      "additionalProperties": false,
      "required": ["type", "content"],
      "properties": {
        "type": {
          "type": "string",
          "enum": ["APPLY_DIRECT_FACT", "RUN_CALCULATOR", "QUERY_KNOWLEDGE", "TEST_OPTION_MAPPING", "CHALLENGE_LEADING_BRANCH"]
        },
        "content": {"type": "string"}
      }
    }
  }
}
```

### Example output

```json
{
  "candidate_leaves_ranked": [
    {
      "leaf_id": "L1",
      "branch_id": "B1",
      "type": "APPLY_DIRECT_FACT",
      "content": "Apply recent long-haul flight as a discriminator against B1/B2/B3",
      "score": 0.82,
      "why": "High-information direct fact strongly separates thromboembolic from infectious explanations"
    },
    {
      "leaf_id": "L2",
      "branch_id": "B3",
      "type": "CHALLENGE_LEADING_BRANCH",
      "content": "Check whether any evidence favors ACS over PE",
      "score": 0.39,
      "why": "Useful challenger probe but lower expected gain"
    }
  ],
  "selected_primary_action": {
    "type": "APPLY_DIRECT_FACT",
    "content": "Apply recent long-haul flight as a discriminator against B1/B2/B3"
  }
}
```

---

## 26.5 `ToolUseGate` output schema

```json
{
  "$id": "ToolUseGateOutput",
  "type": "object",
  "additionalProperties": false,
  "required": ["tool_allowed", "tool_type", "justification", "provenance_requirements"],
  "properties": {
    "tool_allowed": {"type": "boolean"},
    "tool_type": {"type": "string", "enum": ["calculator", "knowledge", "none"]},
    "justification": {"type": "string"},
    "provenance_requirements": {
      "type": "array",
      "items": {"type": "string"}
    }
  }
}
```

### Example output: allowed calculator use

```json
{
  "tool_allowed": true,
  "tool_type": "calculator",
  "justification": "A risk score can be deterministically derived from the explicit stem facts and may change the ranking of leading branches",
  "provenance_requirements": ["store source_ids", "mark independent=false", "log tool justification"]
}
```

### Example output: blocked knowledge retrieval

```json
{
  "tool_allowed": false,
  "tool_type": "knowledge",
  "justification": "Current mode is strict closed-book; retrieval is disabled",
  "provenance_requirements": []
}
```

---

## 26.6 `EvidenceAnnotator` output schema

```json
{
  "$id": "EvidenceAnnotatorOutput",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "result_summary",
    "major_update",
    "calculator_applicable",
    "formal_rule_available",
    "branch_effects",
    "contradiction_detected",
    "reopen_candidates"
  ],
  "properties": {
    "result_summary": {"type": "string"},
    "major_update": {"type": "boolean"},
    "calculator_applicable": {"type": "boolean"},
    "formal_rule_available": {"type": "boolean"},
    "branch_effects": {
      "type": "object",
      "additionalProperties": {
        "type": "string",
        "enum": ["strong_for", "moderate_for", "weak_for", "neutral", "weak_against", "moderate_against", "strong_against"]
      }
    },
    "contradiction_detected": {"type": "boolean"},
    "reopen_candidates": {
      "type": "array",
      "items": {"type": "string"}
    }
  }
}
```

### Example output

```json
{
  "result_summary": "Recent long-haul flight strongly favors PE and mildly argues against infectious causes",
  "major_update": true,
  "calculator_applicable": false,
  "formal_rule_available": false,
  "branch_effects": {
    "B1": "strong_for",
    "B2": "moderate_against",
    "B3": "neutral",
    "B4": "weak_against"
  },
  "contradiction_detected": false,
  "reopen_candidates": []
}
```

---

## 26.7 `PostUpdateStateReviser` output schema

```json
{
  "$id": "PostUpdateStateReviserOutput",
  "type": "object",
  "additionalProperties": false,
  "required": ["branch_decisions"],
  "properties": {
    "branch_decisions": {
      "type": "array",
      "items": {"$ref": "BranchDecision"}
    }
  }
}
```

### Example output

```json
{
  "branch_decisions": [
    {
      "branch_id": "B1",
      "decision": "expand_now",
      "rationale": "Now dominant and still benefits from additional internal discrimination"
    },
    {
      "branch_id": "B2",
      "decision": "park",
      "rationale": "Still plausible but no longer the best-supported explanation"
    },
    {
      "branch_id": "B3",
      "decision": "keep_coarse",
      "rationale": "Dangerous branch retained, but current evidence does not justify expansion"
    }
  ]
}
```

---

## 26.8 `TerminationJudge` output schema

```json
{
  "$id": "TerminationJudgeOutput",
  "type": "object",
  "additionalProperties": false,
  "required": ["ready_to_stop", "termination_type", "reason", "if_continue_next_best_action_type"],
  "properties": {
    "ready_to_stop": {"type": "boolean"},
    "termination_type": {
      "type": "string",
      "enum": ["continue", "confirmation", "actionable_parent", "info_exhaustion", "working_differential"]
    },
    "reason": {"type": "string"},
    "if_continue_next_best_action_type": {
      "type": "string",
      "enum": ["APPLY_DIRECT_FACT", "RUN_CALCULATOR", "QUERY_KNOWLEDGE", "TEST_OPTION_MAPPING", "CHALLENGE_LEADING_BRANCH", "NONE"]
    }
  }
}
```

### Example output

```json
{
  "ready_to_stop": true,
  "termination_type": "confirmation",
  "reason": "One branch now sufficiently dominates and no remaining analytic operation is likely to change the ranking materially",
  "if_continue_next_best_action_type": "NONE"
}
```

---

## 26.9 `AnswerMapper` output schema

```json
{
  "$id": "AnswerMapperOutput",
  "type": "object",
  "additionalProperties": false,
  "required": ["option_scores", "selected_option", "why"],
  "properties": {
    "option_scores": {
      "type": "object",
      "additionalProperties": {"type": "number", "minimum": 0.0, "maximum": 1.0}
    },
    "selected_option": {"type": "string"},
    "why": {"type": "string"}
  }
}
```

### Example output

```json
{
  "option_scores": {
    "A": 0.10,
    "B": 0.74,
    "C": 0.08,
    "D": 0.08
  },
  "selected_option": "B",
  "why": "Option B best matches the dominant PE branch and the strongest discriminative facts"
}
```

---

## 26.10 `FinalAggregator` output schema

```json
{
  "$id": "FinalAggregatorOutput",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "final_mode",
    "leading_diagnosis_or_parent",
    "ranked_differential",
    "coexisting_processes",
    "supporting_evidence",
    "conflicting_evidence",
    "recommended_answer",
    "confidence"
  ],
  "properties": {
    "final_mode": {
      "type": "string",
      "enum": ["single_answer", "ranked_differential"]
    },
    "leading_diagnosis_or_parent": {"type": "string"},
    "ranked_differential": {
      "type": "array",
      "items": {"type": "string"}
    },
    "coexisting_processes": {
      "type": "array",
      "items": {"type": "string"}
    },
    "supporting_evidence": {
      "type": "array",
      "items": {"type": "string"}
    },
    "conflicting_evidence": {
      "type": "array",
      "items": {"type": "string"}
    },
    "recommended_answer": {"type": "string"},
    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
  }
}
```

### Example output

```json
{
  "final_mode": "single_answer",
  "leading_diagnosis_or_parent": "pulmonary embolism",
  "ranked_differential": [
    "pulmonary embolism",
    "infectious pleural or pulmonary cause",
    "acute coronary syndrome or pericardial cause"
  ],
  "coexisting_processes": [],
  "supporting_evidence": [
    "acute pleuritic chest pain",
    "dyspnea",
    "recent long-haul flight"
  ],
  "conflicting_evidence": [
    "no fever or sputum production mentioned"
  ],
  "recommended_answer": "B",
  "confidence": 0.82
}
```

---

## 27. End-to-end example trace: MCQ case

## 27.1 Input

```text
A 46-year-old woman presents with sudden pleuritic chest pain and shortness of breath after a long-haul flight. Which of the following is the most likely diagnosis?
A. Pneumonia
B. Pulmonary embolism
C. Myocardial infarction
D. Panic attack
```

## 27.2 Step 1 — parse vignette

```json
{
  "direct_evidence": [
    {
      "id": "E1",
      "kind": "direct",
      "content": "46-year-old woman",
      "source_ids": [],
      "independent": true,
      "branch_links": {},
      "metadata": {}
    },
    {
      "id": "E2",
      "kind": "direct",
      "content": "sudden pleuritic chest pain",
      "source_ids": [],
      "independent": true,
      "branch_links": {},
      "metadata": {}
    },
    {
      "id": "E3",
      "kind": "direct",
      "content": "shortness of breath",
      "source_ids": [],
      "independent": true,
      "branch_links": {},
      "metadata": {}
    },
    {
      "id": "E4",
      "kind": "direct",
      "content": "recent long-haul flight",
      "source_ids": [],
      "independent": true,
      "branch_links": {},
      "metadata": {}
    }
  ],
  "answer_options": [
    "A. Pneumonia",
    "B. Pulmonary embolism",
    "C. Myocardial infarction",
    "D. Panic attack"
  ]
}
```

## 27.3 Step 2 — root

```json
{
  "root_label": "acute pleuritic chest-pain syndrome with dyspnea",
  "time_course": "acute",
  "supporting_evidence_ids": ["E2", "E3", "E4"],
  "excluded_root_candidates": ["isolated chest pain", "isolated travel history"],
  "need_external_knowledge": false,
  "knowledge_query_if_needed": "",
  "confidence": 0.89
}
```

## 27.4 Step 3 — branches

```json
{
  "branches": [
    {
      "id": "B1",
      "label": "pulmonary embolism",
      "status": "live",
      "prior_estimate": 0.42,
      "danger": 0.92,
      "why_included": "best fit to sudden pleuritic pain, dyspnea, and travel-related risk"
    },
    {
      "id": "B2",
      "label": "infectious pulmonary cause",
      "status": "live",
      "prior_estimate": 0.22,
      "danger": 0.38,
      "why_included": "can cause pleuritic pain and dyspnea"
    },
    {
      "id": "B3",
      "label": "acute coronary or pericardial cause",
      "status": "parked",
      "prior_estimate": 0.18,
      "danger": 0.75,
      "why_included": "dangerous chest-pain branch retained"
    },
    {
      "id": "B4",
      "label": "other",
      "status": "other",
      "prior_estimate": 0.18,
      "danger": 0.10,
      "why_included": "residual bucket"
    }
  ],
  "frontier": ["B1", "B2", "B3"],
  "need_external_knowledge": false,
  "knowledge_query_if_needed": ""
}
```

## 27.5 Step 4 — temporary leaf selection

```json
{
  "candidate_leaves_ranked": [
    {
      "leaf_id": "L1",
      "branch_id": "B1",
      "type": "APPLY_DIRECT_FACT",
      "content": "Apply recent long-haul flight to B1/B2/B3",
      "score": 0.86,
      "why": "High-gain direct discriminator"
    },
    {
      "leaf_id": "L2",
      "branch_id": "B3",
      "type": "CHALLENGE_LEADING_BRANCH",
      "content": "Check whether sudden pleuritic quality weakens ACS/pericardial branch",
      "score": 0.41,
      "why": "Useful challenger pass but lower gain"
    }
  ],
  "selected_primary_action": {
    "type": "APPLY_DIRECT_FACT",
    "content": "Apply recent long-haul flight to B1/B2/B3"
  }
}
```

## 27.6 Step 5 — annotation

```json
{
  "result_summary": "Travel history strongly favors PE over infectious and panic-like explanations",
  "major_update": true,
  "calculator_applicable": false,
  "formal_rule_available": false,
  "branch_effects": {
    "B1": "strong_for",
    "B2": "moderate_against",
    "B3": "neutral",
    "B4": "weak_against"
  },
  "contradiction_detected": false,
  "reopen_candidates": []
}
```

## 27.7 Step 6 — termination

```json
{
  "ready_to_stop": true,
  "termination_type": "confirmation",
  "reason": "The leading branch now dominates and no remaining analytic transformation is likely to reverse the ranking",
  "if_continue_next_best_action_type": "NONE"
}
```

## 27.8 Step 7 — answer mapping

```json
{
  "option_scores": {
    "A": 0.09,
    "B": 0.79,
    "C": 0.06,
    "D": 0.06
  },
  "selected_option": "B",
  "why": "Pulmonary embolism best matches the dominant branch after applying the most discriminative direct evidence"
}
```

---

## 28. End-to-end example trace: calculator-enabled case

## 28.1 Input

```text
A 58-year-old man presents with confusion and tachypnea. Labs: Na 140 mEq/L, Cl 100 mEq/L, HCO3 16 mEq/L. Which of the following best characterizes this acid-base disturbance?
A. Normal anion gap metabolic acidosis
B. High anion gap metabolic acidosis
C. Respiratory alkalosis
D. Metabolic alkalosis
```

## 28.2 Key dynamic
Here calculator use is appropriate because the anion gap is not explicitly given, but can be deterministically computed from provided facts.

## 28.3 Tool gate output

```json
{
  "tool_allowed": true,
  "tool_type": "calculator",
  "justification": "Anion gap can be computed directly from provided electrolytes and is necessary for branch separation",
  "provenance_requirements": ["store source_ids", "mark independent=false", "do not count source electrolytes again independently for the same feature"]
}
```

## 28.4 Derived evidence output

```json
{
  "derived_feature": "anion_gap",
  "value": 24,
  "source_facts": ["Na 140", "Cl 100", "HCO3 16"],
  "independent_evidence": false
}
```

## 28.5 Final answer mapping

```json
{
  "option_scores": {
    "A": 0.05,
    "B": 0.88,
    "C": 0.03,
    "D": 0.04
  },
  "selected_option": "B",
  "why": "Calculated anion gap is elevated, supporting high anion gap metabolic acidosis"
}
```

---

## 29. End-to-end example trace: knowledge-query-enabled case

## 29.1 Mode policy
This trace applies only if `knowledge_mode = whitelisted`.

## 29.2 Input

```text
A young woman presents with a butterfly-shaped facial rash, joint pain, and proteinuria. Which diagnosis is most likely?
A. Rheumatoid arthritis
B. Systemic lupus erythematosus
C. Dermatomyositis
D. Polyarteritis nodosa
```

## 29.3 Tool gate output

```json
{
  "tool_allowed": true,
  "tool_type": "knowledge",
  "justification": "Interpretive mapping of malar rash pattern may be consulted from whitelisted reference knowledge under current mode",
  "provenance_requirements": ["store retrieval source", "mark independent=false", "use only as interpretive mapping"]
}
```

## 29.4 Interpretive evidence output

```json
{
  "knowledge_item": "malar rash is classically associated with systemic lupus erythematosus",
  "role": "interpretive_mapping",
  "supports_fact_to_branch_link": {
    "source_fact": "butterfly-shaped facial rash",
    "target_branch": "systemic lupus erythematosus"
  },
  "independent_evidence": false
}
```

## 29.5 Final answer mapping

```json
{
  "option_scores": {
    "A": 0.07,
    "B": 0.84,
    "C": 0.05,
    "D": 0.04
  },
  "selected_option": "B",
  "why": "The leading branch is SLE, supported by the combination of malar rash, joint pain, and proteinuria"
}
```

---

## 30. Validation rules for implementation

The prototype must fail validation if any of the following occurs:

1. a derived evidence item is marked `independent=true`,
2. an interpretive evidence item is treated as fresh patient evidence,
3. a knowledge query is executed in strict closed-book mode,
4. the controller calls any interactive acquisition method,
5. module output is not valid JSON,
6. answer mapping occurs before branch-state stabilization,
7. unsupported keys appear in strict schema mode.

---

## 31. Recommended test fixtures

### Fixture 1: simple PE-style MCQ
- no calculator
- no retrieval
- direct evidence only

### Fixture 2: acid-base calculator case
- deterministic calculator allowed
- derived evidence provenance tested

### Fixture 3: whitelisted knowledge case
- retrieval allowed
- interpretive evidence tested

### Fixture 4: contradiction case
- challenger should reopen a parked branch

### Fixture 5: forced single-answer collapse case
- multiple plausible branches remain but one answer option must be selected

---

## 32. Codex implementation note

Codex should implement these JSON Schemas as either:
- Pydantic models,
- dataclass validators,
- or explicit schema validation checks,

but strict validation must be enabled at least in development and testing.

The recommended engineering order is:
1. EvidenceItem and parser schema,
2. RootSelector and BranchCreator schemas,
3. TemporaryAnalyticLeafPlanner and ToolUseGate schemas,
4. EvidenceAnnotator and PostUpdateStateReviser schemas,
5. AnswerMapper and FinalAggregator schemas,
6. end-to-end trace tests using the examples above.

