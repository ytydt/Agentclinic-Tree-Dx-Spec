#!/usr/bin/env python3
"""Rebuild anchored prior-design coverage; no clinical/production execution."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
BASE = "bbc036e8a6ec93583be915a4609fe86278ed062c"
PREFIX = "analysis/mechanism_v2/results/"
DESIGN = PREFIX + "RULE_EXTRACTION_EXECUTION_REDESIGN/"
MECH = PREFIX + "RAG_GUIDELINE_ORACLE_CEILING_LOCAL/"
SOURCES = {}


def read(path):
    if path not in SOURCES:
        raw = subprocess.run(["git", "show", f"{BASE}:{path}"], cwd=ROOT,
                             check=True, capture_output=True, timeout=45).stdout
        if raw.startswith(b"version https://git-lfs.github.com/spec/"):
            raise ValueError(f"LFS pointer cannot be audited as source: {path}")
        SOURCES[path] = {"path": path, "sha256": hashlib.sha256(raw).hexdigest(),
                         "text": raw.decode("utf-8"), "read_via": "git_blob_at_frozen_commit"}
    return SOURCES[path]["text"]


def anchor(path, needle):
    hits = [(i, line) for i, line in enumerate(read(path).splitlines(), 1) if needle in line]
    if len(hits) != 1:
        raise AssertionError((path, needle, len(hits)))
    line, excerpt = hits[0]
    return {"path": path, "line": line, "excerpt": excerpt}


def a(name, needle):
    return anchor(DESIGN + name, needle)


def item(cid, concern, mids, coverage, anchors, remaining, classification):
    return dict(id=cid, concern=concern, prior_migration_ids=mids,
                prior_coverage=coverage, anchors=anchors,
                remaining_delivery_requirement=remaining,
                classification=classification,
                prior_implementation_status="proposal_not_implemented")


def main():
    items = [
        item("PC01", "错误疾病主语/首个模糊命中抢走后续精确命中", ["M10", "M11"], "explicit",
             [a("REPORT.md", "正确原始subject仍会被程序送错候选"), a("REPORT.md", "同义名、父子关系、病因/病灶/表现")],
             "拆分列表顺序/身份键等可确定代码错误与未知术语等价、父子继承、因果组件的语义问题；建立反合并及真别名正例。", "code_defect_plus_semantic_linking_limitation"),
        item("PC02", "不同源窗口的规则组意外合并", ["M13"], "explicit",
             [a("EXTRACTION_PROTOCOL.md", "跨窗口局部ID不能合并")],
             "证明组合键各字段如何造成碰撞；区分原始subject不同与错归同一候选，不把所有冲突称为跨疾病组自动合并。", "identity_and_referential_integrity_defect"),
        item("PC03", "原子去重删掉组成员，未将成员边重定向到共享规范原子", ["M12", "M13"], "explicit",
             [a("REPORT.md", "若同一个叶命题用于两个真实组"), a("EXTRACTION_PROTOCOL.md", "shared leaf不删除occurrence")],
             "对共享叶、singleton退化、成员计数、后继组动作分别提供最小复现；明确当前是删除边而非保留显式空占位。", "ordering_and_referential_integrity_defect"),
        item("PC04", "谓词字符串去重不足，同时阈值/范围不同的规则可能误去重", ["M12", "M20"], "explicit",
             [a("SEMANTIC_CONTRACT.md", "源规则身份、语义等价/派生关系、重复曝光记录")],
             "完整命题结构的确定性去重与自由文本语义等价识别分开；同义扩充须有反向检验，不能只提升合并召回。", "code_defect_plus_semantic_equivalence_limitation"),
        item("PC05", "竞争语句条数被当定向反证条数", ["M20", "M22"], "explicit",
             [a("REPORT.md", "L4不应遍历一个含`distinguishes`标签的原子就广播处罚")],
             "复现无真正discriminator、否定/阈值未满足、跨组、重复与不合格上下文如何仍产生L4；合法定向对比须保留正例。", "invalid_directional_scoring_policy_and_missing_admission_checks"),
        item("PC06", "无直接得分行通过claimants改写其他候选权重", ["M19"], "explicit",
             [a("REPORT.md", "49的epidemiology行无直接分值却进入claimants")],
             "以不合格行插入不变性检查隐藏影响，另报合法证据删除后的全候选重加权。", "admission_ordering_defect"),
        item("PC07", "去重保留前行出处却升级为后行最大模态", ["M12"], "explicit",
             [anchor(MECH + "run_mechanical_engine.py", "prev[\"modality\"] = a.get(\"modality\")")],
             "新增能改变执行效力的顺序置换复现，原始出处不可因最大模态产生合成证据。", "cross_record_mutation_defect"),
        item("PC08", "组根效力缺失、all混同必要性、成员真值不一致", ["M04", "M16", "M17", "M18"], "explicit",
             [a("REPORT.md", "连词、量词、模态与诊断效果是不同维度"), a("REPORT.md", "历史实现已有浅层")],
             "先描述现有启用profile再证明执行违例；关闭有意消融不等于修复全部组语义。", "specification_gap_plus_execution_defect"),
        item("PC09", "治疗、检查、诊断没有完整用途/动作类型", ["M05", "M08", "M18", "M19"], "explicit_principle_partial_executable_contract",
             [a("REPORT.md", "| 检查、治疗、工作流 |"), a("EXTRACTION_PROTOCOL.md", "原文所指对象与任务：诊断")],
             "补充规则用途、动作客体、行动模态、临床事实状态、消费者准入矩阵与未知用途政策；不是首次提出阶段分离。", "typed_action_contract_gap"),
        item("PC10", "建议检查与实际阳性结果混同", ["M05", "M14", "M18"], "explicit_principle_partial_executable_contract",
             [a("SEMANTIC_CONTRACT.md", "病例说“安排了某项检查”"), a("REPORT.md", "一个检查被做过、检查异常、某项具体结果为阳性")],
             "细化recommended/ordered/performed/result_observed的证据类型、target非疾病时的结构以及禁反向诊断桥接。", "event_status_and_action_type_gap"),
        item("PC11", "人群、场景、时间适用范围未执行", ["M04", "M14", "M18"], "explicit_principle_partial_executable_contract",
             [a("SEMANTIC_CONTRACT.md", "| `applicability` |"), a("EXTRACTION_PROTOCOL.md", "人群、人物角色、部位、时间")],
             "补充scope继承、缺省范围、未知年龄、范围不适用与疾病false的区别；不能把既有applicability槽位写成新发明。", "runtime_scope_interpreter_gap"),
        item("PC12", "儿童/成人等分支、重叠范围和else策略", ["M04", "M18"], "partial",
             [a("EXTRACTION_PROTOCOL.md", "规则组、完整评分表、工作流分支都作为整体保留"), a("SEMANTIC_CONTRACT.md", "applicability = TRUE")],
             "原提案未完整定义分支选择、未知guard、显式优先级、互斥/覆盖检查、默认分支来源及相互冲突动作，需独立补充。", "branch_dispatch_and_policy_specification_gap"),
        item("PC13", "规则群中病例事实/阈值/角色错接", ["M07", "M14", "M15", "M16", "M21"], "explicit",
             [a("REPORT.md", "正常ECG") if "正常ECG" in read(DESIGN + "REPORT.md") else a("REPORT.md", "QTc 380与异常区间")],
             "类型、单位、数值比较可独立代码修复；概念同一性、标本/时序信息提取仍需新方法或人工词典与测评。", "code_defect_plus_information_loss_and_semantic_matching"),
        item("PC14", "出处、缓存、解析失败和隐式全局配置", ["M01", "M02", "M03", "M06", "M09", "M25"], "explicit",
             [a("REPORT.md", "旧缓存键"), a("REPORT.md", "可选NLI路径")],
             "精确列默认运行与可选未启用路径；缓存键和异常状态可修，但完整来源及源句语义仍是另外验收对象。", "provenance_and_reproducibility_defect"),
        item("PC15", "trace/终点/proxy以及干预口径", ["M23", "M24"], "explicit",
             [a("REPORT.md", "排序结果须分别报告完整目标")],
             "修观察器与指标不等于运行引擎临床错误修复；proxy历史约定保留，新增完整终点不可偷偷覆盖历史值。", "observability_defect_or_evaluation_convention"),
    ]
    migration = json.loads(read(DESIGN + "migration_matrix.json"))
    byid = {m["id"]: m for m in migration["migration_items"]}
    for row in items:
        for mid in row["prior_migration_ids"]:
            assert byid[mid]["implementation_status"] == "proposal_not_implemented"
        row["migration_anchors"] = [{"id": mid, "title": byid[mid]["title"],
                                      "minimum_fix": byid[mid]["minimum_fix"]}
                                     for mid in row["prior_migration_ids"]]

    kg = "src/agentclinic_tree_dx/knowledge/guideline_kg_schema.py"
    kge = "src/agentclinic_tree_dx/knowledge/guideline_kg_extraction.py"
    reuse = [
        {"id": "KR01", "capability": "typed terminology mappings and typed concept roles",
         "anchors": [anchor(kg, "MAPPING_PREDICATES = {"), anchor(kg, "class ConceptMapping(_KGRecord):"), anchor(kg, "class DiagnosisExpression(_KGRecord):")],
         "reuse": "stable identities, exact/broad/narrow/related edge distinctions and structure validators",
         "not_guaranteed": "unknown aliases are not clinically certified by schema; related/broad/narrow cannot become equality"},
        {"id": "KR02", "capability": "recursive logic with references and cycle validation",
         "anchors": [anchor(kg, "LOGIC_OPERATORS ="), anchor(kg, 'def _validate_logic_cycles('), anchor(kg, 'errors.append("operand_ids: duplicate operands are not allowed")')],
         "reuse": "dangling-reference, typed operand, duplicate-member, operator arity and cycle checks",
         "not_guaranteed": "no finite/general quantifier binding, runtime K3, member-source completeness or distinct clinical witnesses is established"},
        {"id": "KR03", "capability": "population, measurement, specimen and temporal qualifiers",
         "anchors": [anchor(kg, "population_context_ids: tuple[str, ...] = ()"), anchor(kg, "class FeaturePattern(_KGRecord):"), anchor(kg, 'f"{prefix}.population_context_ids: concept must be population"')],
         "reuse": "typed record fields and cross-record domain/range checks",
         "not_guaranteed": "population list is not an evaluated applicability expression; no age cutoff/branch priority/unknown guard semantics follows"},
        {"id": "KR04", "capability": "differential list membership kept separate from directional evidence",
         "anchors": [anchor(kge, '"""Compile WikEM link lists as candidate-membership, never as criteria."""'), anchor(kge, '"enumeration_only": True,')],
         "reuse": "enumeration_only/ranking_eligible=false authoring contract; separate non-ranking export lane",
         "not_guaranteed": "flags must be honored at every runtime consumer; generated clinical assertion correctness is not certified"},
        {"id": "KR05", "capability": "reference and evidence graph integrity",
         "anchors": [anchor(kg, "def validate_graph(records:"), anchor(kg, "def _validate_cross_record("), anchor(kg, "class GraphValidationIndex:")],
         "reuse": "deterministic shape/reference/evidence-offset validation and atomic delta validation",
         "not_guaranteed": "quote exactness is not entailment; complete graph shape is not faithful extraction or approved diagnostic action"},
    ]
    frozen_runtime = [MECH + p for p in ["run_trial_extraction.py", "run_mechanical_engine.py", "gate_assertions.py", "score_2x2_engine.py", "run_trial_retrieval.py", "trial_retriever.py"]]
    forbidden = ["guideline_kg_schema", "LogicExpression", "DiagnosticAssertion", "population_context_ids", "ranking_eligible"]
    scans = [{"path": p, "searched_tokens": forbidden,
              "hits": [token for token in forbidden if token in read(p)]} for p in frozen_runtime]
    assert all(not row["hits"] for row in scans)
    payload = dict(schema_version=1, frozen_commit=BASE, evidence_date="2026-09-08",
                   scope="prior-design coverage and selected internal reuse; not exhaustive separate KG audit",
                   coverage_items=items, internal_reuse= reuse,
                   mechanical_integration_scan=scans,
                   integration_scan_limit="No references in the six named frozen runtime files; not a claim about every repository consumer.",
                   sources=[{k:v for k,v in source.items() if k != "text"} for source in SOURCES.values()])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "prior_coverage_map.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    validation = dict(status="passed", frozen_commit=BASE, coverage_items=len(items), internal_reuse_entries=len(reuse),
                      anchor_count=sum(len(x["anchors"]) for x in items+reuse), source_files=len(SOURCES),
                      mechanical_files_scanned=len(scans), claim="source anchor and frozen coverage consistency only")
    (OUT / "prior_coverage_validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(validation, ensure_ascii=False))


if __name__ == "__main__":
    main()
