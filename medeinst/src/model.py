"""
MedEinst / ECR-Agent — Dynamic Causal Inference.

Paper: https://arxiv.org/abs/2601.06636
Authors: Wenting Chen, Zhongrui Zhu, Guolin Huang, Wenxuan Wang (2026)

Implements: Dual-pathway perception, three-level DCGR, evidence audit (Alg. 2).

Section references:
  §4.2.1 — Dual-Pathway Perception
  §4.2.2 — Dynamic Causal Graph Reasoning (association / intervention / counterfactual)
  §4.2.3 — Evidence Audit and S(d)
  Appendix A.3 — graph schema, merge-or-prune τ=0.9
  Algorithm 2 lines 17–50 — DCI_PIPELINE
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Mapping

from src import prompts
from src.llm import EchoLLM, LLMClient
from src.loss import ScoreWeights, evidence_score, pick_diagnosis
from src.utils import parse_json_object, pairwise_cosine


@dataclass
class ModelConfig:
    """All DCI hyperparameters. Values from the paper unless [UNSPECIFIED]."""

    top_k: int = 5  # Appendix C — k = 5
    merge_tau: float = 0.9  # Eq. 2
    w_match: float = 1.0  # [UNSPECIFIED] §4.2.3 weights
    w_conflict: float = 1.0
    w_shadow: float = 1.0
    # Extra S(d) terms: paper formula ignores support/rule-out. Default 0.
    w_support: float = 0.0
    w_ruleout: float = 0.0
    w_pivot: float = 0.0
    generic_match_scale: float = 1.0
    absent_match_as_conflict: bool = False
    score_normalize: str = "none"  # none | n_k | n_scored
    disqualify_absent_pivot: bool = False
    # llm | argmax | cot_unless_margin | cot1 | auto
    # auto: DA keeps LLM audit, MCR keeps CoT@1 (held-out ablation).
    audit_mode: str = "llm"
    override_margin: float = 0.0
    tie_break: str = "cot1"
    audit_include_intuition: bool = True
    exemplar_k: int = 3  # [UNSPECIFIED]
    live_search_pubmed: bool = True  # §4.2.2
    live_search_opentargets: bool = True
    # Parent HybridCPGRetriever QUERY_ENCODER; paper Eq. 2 unnamed
    embedding: str = "medcpt"

    @classmethod
    def from_mapping(cls, model_cfg: Mapping[str, Any], *, live_search: bool | None = None) -> ModelConfig:
        cfg = dict(model_cfg or {})
        if live_search is False:
            cfg["live_search_pubmed"] = False
            cfg["live_search_opentargets"] = False
        known = {name for name in cls.__dataclass_fields__}
        payload = {k: cfg[k] for k in cfg if k in known}
        if "score_normalize" not in payload and "normalize" in cfg:
            payload["score_normalize"] = cfg["normalize"]
        return cls(**payload)


def resolve_audit_mode(config: ModelConfig, slice_name: str | None = None) -> str:
    """auto = LLM audit on DiagnosisArena, CoT@1 on open MCR (held-out ablation)."""
    mode = str(config.audit_mode or "llm").strip().lower()
    if mode == "auto":
        text = str(slice_name or "")
        if text.startswith("d2_") or "diagnosisarena" in text:
            return "llm"
        return "cot1"
    return mode


def _score_weights(config: ModelConfig) -> ScoreWeights:
    return ScoreWeights(
        w_match=float(config.w_match),
        w_conflict=float(config.w_conflict),
        w_shadow=float(config.w_shadow),
        w_support=float(config.w_support),
        w_ruleout=float(config.w_ruleout),
        w_pivot=float(config.w_pivot),
        generic_match_scale=float(config.generic_match_scale),
        absent_match_as_conflict=bool(config.absent_match_as_conflict),
        normalize=str(config.score_normalize or "none"),
        disqualify_absent_pivot=bool(config.disqualify_absent_pivot),
        override_margin=float(config.override_margin),
        tie_break=str(config.tie_break or "cot1"),
        audit_mode=str(config.audit_mode or "llm"),
    )


@dataclass
class PNode:
    """§4.2.1 / A.3 Patient Nodes VP with status s(p) ∈ {Present, Absent, Missing}."""

    id: str
    content: str
    original_text: str
    status: str  # Present | Absent | Missing


@dataclass
class GraphNode:
    """A.3 schema: patient / knowledge / disease / shadow nodes."""

    id: str
    kind: str
    content: str
    status: str | None = None
    ktype: str | None = None  # Pivot | General for knowledge nodes


@dataclass
class GraphEdge:
    """§4.2.2 relations: conflict, matching, rule out, support, penalty."""

    src: str
    dst: str
    relation: str


@dataclass
class CausalGraph:
    """G_ill = (Vd, Vp, Vk; E) then G', G† after forward/backward (§4.2.2)."""

    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    disease: str = ""

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        self.edges.append(edge)

    def nodes_touching_disease(self, disease: str) -> set[str]:
        ids = {n.id for n in self.nodes.values() if n.kind == "disease" and n.content == disease}
        if not ids:
            ids = {n.id for n in self.nodes.values() if n.kind == "disease"}
        frontier = set(ids)
        for edge in self.edges:
            if edge.src in ids or edge.dst in ids:
                frontier.add(edge.src)
                frontier.add(edge.dst)
        for node in self.nodes.values():
            if node.kind in {"patient", "knowledge", "shadow"}:
                frontier.add(node.id)
        return frontier


@dataclass
class DCIResult:
    """Algorithm 2 line 49 — return (d⋆, G_ill^{d⋆})."""

    diagnosis: str
    graph: CausalGraph
    dset: list[str]
    p_obs: list[PNode]
    scores: dict[str, float]
    graph_summary: dict[str, Any]
    intuition: str


def _nid(prefix: str, content: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in content)[:48]
    return f"{prefix}_{slug}"


class DualPathwayPerception:
    """§4.2.1 — parallel intuitive Top-k CoT and analytic problem representation."""

    def __init__(self, llm: LLMClient, top_k: int) -> None:
        self.llm = llm
        self.top_k = top_k

    def intuitive(self, x: str, feedback: str | None = None) -> tuple[list[str], str]:
        # Appendix C — zero-shot CoT, k=5
        user = f"k = {self.top_k}\n\nPatient narrative:\n{x}"
        if feedback:
            user = prompts.INTUITIVE_RETRY_PREFIX + feedback + "\n\n" + user
        raw = self.llm.complete(prompts.INTUITIVE_SYSTEM, user)
        try:
            obj = parse_json_object(raw)
            names = [str(item["name"]) for item in obj["diagnoses"][: self.top_k]]
        except (ValueError, KeyError, TypeError):
            names = []
        if not names:
            names = [line.strip("- ") for line in raw.splitlines() if line.strip()][: self.top_k]
        return names[: self.top_k], raw

    def analytic(self, x: str) -> tuple[str, list[PNode]]:
        raw = self.llm.complete(prompts.ANALYTIC_SYSTEM, f"Patient narrative:\n{x}")
        try:
            obj = parse_json_object(raw)
        except ValueError:
            obj = {}
        one_liner = str(obj.get("problem_representation_one_liner", ""))
        nodes: list[PNode] = []
        for i, row in enumerate(obj.get("p_nodes") or []):
            status = str(row.get("status", "Missing"))
            # Table A7 RULES: Absent only for explicit no/denies/without
            if status == "Absent":
                orig = str(row.get("original_text", "")).lower()
                if not any(tok in orig for tok in ("no ", "denies", "without", "no,", " not ")):
                    status = "Missing"
            nodes.append(
                PNode(
                    id=str(row.get("id") or f"p{i}"),
                    content=str(row.get("content", "")),
                    original_text=str(row.get("original_text", "")),
                    status=status,
                )
            )
        return one_liner, nodes


def merge_or_prune(
    script_nodes: list[GraphNode],
    p_obs: list[PNode],
    tau: float,
) -> list[GraphNode]:
    """Eq. 2 / A.3 — Merge if cos(e_pscript, e_pobs) > τ else Prune. τ=0.9."""
    kept: list[GraphNode] = []
    for script in script_nodes:
        best = 0.0
        for obs in p_obs:
            best = max(best, pairwise_cosine(script.content, obs.content))
        if best > tau:
            kept.append(script)
    # §4.2.2 — "merging novel observations"
    existing = {pairwise_cosine(k.content, k.content) for k in kept}
    for obs in p_obs:
        if any(pairwise_cosine(obs.content, k.content) > tau for k in kept):
            continue
        kept.append(
            GraphNode(
                id=obs.id,
                kind="patient",
                content=obs.content,
                status=obs.status,
            )
        )
        _ = existing
    return kept


_PUBMED_LOCK = threading.Lock()
_PUBMED_NEXT = 0.0
_PUBMED_MIN_INTERVAL = 0.35  # NCBI unauthenticated cap is ~3 req/s


def _wait_pubmed_slot() -> None:
    global _PUBMED_NEXT
    with _PUBMED_LOCK:
        now = time.monotonic()
        wait = _PUBMED_NEXT - now
        _PUBMED_NEXT = max(now, _PUBMED_NEXT) + _PUBMED_MIN_INTERVAL
    if wait > 0:
        time.sleep(wait)


def live_search_pubmed(disease: str, retmax: int = 5) -> list[str]:
    """§4.2.2 / Appendix C — PubMed as analytic-system extension."""
    params = urllib.parse.urlencode(
        {"db": "pubmed", "term": f"{disease}[Title/Abstract]", "retmax": retmax, "retmode": "json"}
    )
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + params
    try:
        _wait_pubmed_slot()
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ids = data.get("esearchresult", {}).get("idlist") or []
        if not ids:
            return []
        fetch = urllib.parse.urlencode(
            {"db": "pubmed", "id": ",".join(ids), "retmode": "xml", "rettype": "abstract"}
        )
        furls = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + fetch
        _wait_pubmed_slot()
        with urllib.request.urlopen(furls, timeout=20) as resp:
            xml = resp.read()
        root = ET.fromstring(xml)
        abstracts: list[str] = []
        for node in root.iter("AbstractText"):
            if node.text:
                abstracts.append(node.text.strip())
        return abstracts[:retmax]
    except (OSError, json.JSONDecodeError, ET.ParseError):
        return []


def live_search_opentargets(disease: str) -> list[str]:
    """§4.2.2 / Appendix C — OpenTargets structured query.

    [UNSPECIFIED] exact GraphQL document is not in the paper.
    """
    query = {
        "query": """
        query Search($q: String!) {
          search(queryString: $q, entityNames: ["disease"], page: {index: 0, size: 3}) {
            hits { id name description }
          }
        }
        """,
        "variables": {"q": disease},
    }
    req = urllib.request.Request(
        "https://api.platform.opentargets.org/api/v4/graphql",
        data=json.dumps(query).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        hits = (((payload.get("data") or {}).get("search") or {}).get("hits")) or []
        out: list[str] = []
        for hit in hits:
            desc = hit.get("description") or hit.get("name") or ""
            if desc:
                out.append(str(desc))
        return out
    except (OSError, json.JSONDecodeError, KeyError):
        return []


class DynamicCausalGraphReasoning:
    """§4.2.2 — association init, intervention forward, counterfactual backward."""

    def __init__(self, llm: LLMClient, config: ModelConfig) -> None:
        self.llm = llm
        self.config = config

    def initialize(
        self,
        disease: str,
        p_obs: list[PNode],
        illness_graph: CausalGraph | None,
    ) -> CausalGraph:
        # Alg. 2 steps 24–27
        g = CausalGraph(disease=disease)
        g.add_node(GraphNode(id=_nid("d", disease), kind="disease", content=disease))
        script = []
        if illness_graph is not None:
            script = [n for n in illness_graph.nodes.values() if n.kind == "patient"]
        merged = merge_or_prune(script, p_obs, self.config.merge_tau)
        if not merged:
            merged = [
                GraphNode(id=p.id, kind="patient", content=p.content, status=p.status)
                for p in p_obs
            ]
        for node in merged:
            g.add_node(node)
        return g

    def forward(self, graph: CausalGraph, disease: str, p_obs: list[PNode]) -> CausalGraph:
        # Alg. 2 steps 28–31 LiveSearch + Link
        snippets: list[str] = []
        if self.config.live_search_pubmed:
            snippets.extend(live_search_pubmed(disease))
        if self.config.live_search_opentargets:
            snippets.extend(live_search_opentargets(disease))
        knowledge_blob = "\n".join(snippets) if snippets else "(no live hits; LLM parametric knowledge only)"
        user = (
            f"Candidate disease: {disease}\n"
            f"Other context nodes: {[p.content for p in p_obs]}\n"
            f"Retrieved knowledge:\n{knowledge_blob}"
        )
        raw = self.llm.complete(prompts.PIVOT_SYSTEM, user)
        try:
            k_nodes = parse_json_object(raw).get("k_nodes") or []
        except ValueError:
            k_nodes = []
        d_id = _nid("d", disease)
        for i, kn in enumerate(k_nodes):
            content = str(kn.get("content", ""))
            ktype = str(kn.get("type", "Pivot"))
            kid = _nid("k", f"{i}_{content}")
            graph.add_node(GraphNode(id=kid, kind="knowledge", content=content, ktype=ktype))
            # Alg. 2 line 31 Link(Vd, Vk) ∪ Link(Vk, Vp)
            if ktype == "Pivot" and kn.get("ruled_out_candidates"):
                graph.add_edge(GraphEdge(src=d_id, dst=kid, relation="rule out"))
            else:
                graph.add_edge(GraphEdge(src=d_id, dst=kid, relation="support"))
        self._tag_vp_vk(graph, p_obs)
        return graph

    def _tag_vp_vk(self, graph: CausalGraph, p_obs: list[PNode]) -> None:
        # §4.2.2 Qwen3-32B: Vp↔Vk conflict|matching
        k_nodes = [n for n in graph.nodes.values() if n.kind == "knowledge"]
        if not k_nodes or not p_obs:
            return
        payload = {
            "patients": [{"id": p.id, "content": p.content, "status": p.status} for p in p_obs],
            "knowledge": [{"id": n.id, "content": n.content} for n in k_nodes],
        }
        raw = self.llm.complete(prompts.RELATION_SYSTEM, json.dumps(payload, ensure_ascii=False))
        try:
            rels = parse_json_object(raw).get("relations") or []
        except ValueError:
            rels = []
        allowed = {"conflict", "matching", "rule out", "support"}
        for rel in rels:
            relation = str(rel.get("relation", ""))
            if relation not in allowed:
                continue
            graph.add_edge(
                GraphEdge(
                    src=str(rel.get("src", "")),
                    dst=str(rel.get("dst", "")),
                    relation=relation,
                )
            )

    def backward(self, graph: CausalGraph, disease: str, x: str, p_obs: list[PNode]) -> CausalGraph:
        # Alg. 2 steps 32–41: Δ_miss, ReExamine, shadow nodes
        present = {p.content.lower() for p in p_obs if p.status == "Present"}
        k_nodes = [n for n in graph.nodes.values() if n.kind == "knowledge"]
        for kn in k_nodes:
            if any(pairwise_cosine(kn.content, p) > self.config.merge_tau for p in present):
                continue
            raw = self.llm.complete(
                prompts.REEXAMINE_SYSTEM,
                f"Finding: {kn.content}\n\nNarrative:\n{x}",
            )
            try:
                verdict = str(parse_json_object(raw).get("verdict", "NotFound"))
            except ValueError:
                verdict = "NotFound"
            if verdict == "Found":
                pid = _nid("p_found", kn.content)
                graph.add_node(
                    GraphNode(id=pid, kind="patient", content=kn.content, status="Present")
                )
                graph.add_edge(GraphEdge(src=pid, dst=kn.id, relation="matching"))
            else:
                sid = _nid("shadow", kn.content)
                graph.add_node(GraphNode(id=sid, kind="shadow", content=kn.content))
                graph.add_edge(
                    GraphEdge(src=sid, dst=_nid("d", disease), relation="penalty")
                )
        return graph


class EvidenceAudit:
    """§4.2.3 / Alg. 2 lines 46–48 — scores, graph summary, exemplars, LLM judge."""

    def __init__(self, llm: LLMClient, config: ModelConfig) -> None:
        self.llm = llm
        self.config = config

    def summarize(self, graphs: dict[str, CausalGraph], scores: dict[str, float]) -> dict[str, Any]:
        # k disease-centric subgraphs
        return {
            d: {
                "score": scores[d],
                "nodes": [
                    {"id": n.id, "kind": n.kind, "content": n.content, "ktype": n.ktype, "status": n.status}
                    for n in g.nodes.values()
                ],
                "edges": [{"src": e.src, "dst": e.dst, "relation": e.relation} for e in g.edges],
            }
            for d, g in graphs.items()
        }

    def retrieve_exemplars(
        self,
        p_obs: list[PNode],
        memory: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        # Alg. 2 line 47 RetrieveExemplars(M, Pobs)
        query = " ".join(p.content for p in p_obs)
        ranked = sorted(
            memory,
            key=lambda row: pairwise_cosine(query, str(row.get("x", ""))),
            reverse=True,
        )
        return ranked[: self.config.exemplar_k]

    def judge(
        self,
        dset: list[str],
        scores: dict[str, float],
        summary: dict[str, Any],
        exemplars: list[dict[str, Any]],
        intuition: str,
    ) -> str:
        user = json.dumps(
            {
                "intuition": intuition if self.config.audit_include_intuition else "",
                "candidates": dset,
                "scores": scores,
                "graph_summary": summary,
                "exemplars": [
                    {"y_gt": e.get("y_gt"), "x": str(e.get("x", ""))[:500]} for e in exemplars
                ],
            },
            ensure_ascii=False,
        )
        raw = self.llm.complete(prompts.AUDIT_SYSTEM, user)
        try:
            return str(parse_json_object(raw).get("diagnosis") or dset[0])
        except (ValueError, IndexError):
            if scores:
                return max(scores.items(), key=lambda kv: kv[1])[0]
            return dset[0] if dset else ""


class ECRAgent:
    """§4 ECR-Agent — DCI_PIPELINE (Algorithm 2 lines 17–50)."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        config: ModelConfig | None = None,
        illness_graphs: dict[str, CausalGraph] | None = None,
        exemplar_base: list[dict[str, Any]] | None = None,
    ) -> None:
        self.llm = llm or EchoLLM()
        self.config = config or ModelConfig()
        from src.embed import configure_embedding

        configure_embedding(self.config.embedding)
        self.perception = DualPathwayPerception(self.llm, self.config.top_k)
        self.dcgr = DynamicCausalGraphReasoning(self.llm, self.config)
        self.audit = EvidenceAudit(self.llm, self.config)
        self.illness_graphs = illness_graphs if illness_graphs is not None else {}
        self.exemplar_base = exemplar_base if exemplar_base is not None else []

    def dci_pipeline(
        self,
        x: str,
        feedback: str | None = None,
        *,
        slice_name: str | None = None,
        audit_mode: str | None = None,
    ) -> DCIResult:
        mode = (audit_mode or resolve_audit_mode(self.config, slice_name)).strip().lower()
        dset, intuition = self.perception.intuitive(x, feedback=feedback)
        if mode == "cot1":
            diagnosis = dset[0] if dset else ""
            return DCIResult(
                diagnosis=diagnosis,
                graph=CausalGraph(),
                dset=dset,
                p_obs=[],
                scores={},
                graph_summary={},
                intuition=intuition,
            )
        _one_liner, p_obs = self.perception.analytic(x)
        graphs: dict[str, CausalGraph] = {}
        scores: dict[str, float] = {}
        weights = _score_weights(self.config)
        for disease in dset:
            prior = self.illness_graphs.get(disease)
            g = self.dcgr.initialize(disease, p_obs, prior)
            g = self.dcgr.forward(g, disease, p_obs)
            g = self.dcgr.backward(g, disease, x, p_obs)
            graphs[disease] = g
            scores[disease] = evidence_score(g, disease, weights=weights)
        summary = self.audit.summarize(graphs, scores)
        exemplars = self.audit.retrieve_exemplars(p_obs, self.exemplar_base)
        cot1 = dset[0] if dset else ""
        if mode in {"argmax", "cot_unless_margin"}:
            diagnosis = pick_diagnosis(
                dset,
                scores,
                cot1=cot1,
                override_margin=self.config.override_margin if mode == "cot_unless_margin" else 0.0,
                tie_break=self.config.tie_break,
            )
        else:
            diagnosis = self.audit.judge(dset, scores, summary, exemplars, intuition)
        chosen = graphs.get(diagnosis) or next(iter(graphs.values()), CausalGraph())
        return DCIResult(
            diagnosis=diagnosis,
            graph=chosen,
            dset=dset,
            p_obs=p_obs,
            scores=scores,
            graph_summary=summary,
            intuition=intuition,
        )
