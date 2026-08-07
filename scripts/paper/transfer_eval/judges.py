"""Lexical and LLM judges for OX/MCR official eval."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
from pathlib import Path
from typing import Any, Mapping, Optional

_PAPER = Path(__file__).resolve().parents[1]
_ROOT = Path(__file__).resolve().parents[3]
if str(_PAPER) not in sys.path:
    sys.path.insert(0, str(_PAPER))
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from mapper_bind_repair import leaf_match_score  # noqa: E402

from .matching import DEFAULT_LEXICAL_THRESHOLD  # noqa: E402

JUDGE_MODEL_SLUG = "google/gemini-2.5-flash"
JUDGE_MODEL_SHORT = "gemini-2.5-flash"
JUDGE_ENV = "gnn-llm"
JUDGE_VPN = "clashon"
# Formal LLM eval concurrency (JUDGE_MODEL_CONTRACT.md).
JUDGE_WORKERS = 50

PROMPTS_DIR = _ROOT / "analysis" / "transfer_metrics_v1" / "judge_prompts"

_PROMPT_FILES = {
    "ox.ddx_match": "ox_appendix3_diagnosis_match.md",
    "ox.interpretation_consistency": "ox_appendix3_interpretation_consistency.md",
    "mcr.diag_accuracy": "mcr_prompt7_diagnostic_accuracy.md",
    "mcr.reasoning_recall": "mcr_prompt5_reasoning_recall.md",
}

_TEMPLATE_FENCE = re.compile(r"```\n(.*?)```", re.DOTALL)
_YN = re.compile(r"\b([yn]|yes|no)\b", re.I)
_BIT = re.compile(r"[{'\"]?\s*([01])\s*[}'\"]?")


def _extract_template(md_text: str) -> str:
    m = _TEMPLATE_FENCE.search(md_text)
    if not m:
        raise ValueError("no fenced template in prompt md")
    return m.group(1).strip()


def load_prompt_template(prompt_id: str) -> tuple[str, str]:
    """Return (template_text, sha256_hex of file bytes)."""
    name = _PROMPT_FILES.get(prompt_id)
    if not name:
        raise KeyError("unknown prompt_id: %s" % prompt_id)
    path = PROMPTS_DIR / name
    raw = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return _extract_template(raw), digest


def prompt_hash(prompt_id: str) -> str:
    _, digest = load_prompt_template(prompt_id)
    return digest[:16]


def parse_ox_bit(response: str) -> Optional[int]:
    text = str(response or "").strip()
    if not text:
        return None
    # Prefer last 0/1 occurrence (models often reason then answer)
    hits = _BIT.findall(text)
    if hits:
        return int(hits[-1])
    return None


def parse_yn(response: str) -> Optional[bool]:
    text = str(response or "").strip().lower()
    if not text:
        return None
    m = _YN.search(text)
    if not m:
        return None
    tok = m.group(1).lower()
    return tok in {"y", "yes"}


def parse_reasoning_matching_dict(response: str) -> dict[str, list[str]]:
    text = str(response or "")
    # Prefer ```json block
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL | re.I)
    blob = m.group(1) if m else None
    if blob is None:
        m2 = re.search(r"(\{\s*\"matching_dict\".*\})", text, re.DOTALL)
        blob = m2.group(1) if m2 else None
    if not blob:
        return {}
    try:
        doc = json.loads(blob)
    except json.JSONDecodeError:
        return {}
    md = doc.get("matching_dict") if isinstance(doc, Mapping) else None
    if not isinstance(md, Mapping):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in md.items():
        if isinstance(v, list):
            out[str(k)] = [str(x) for x in v]
        elif v:
            out[str(k)] = [str(v)]
        else:
            out[str(k)] = []
    return out


class JudgeCache:
    def __init__(self, path: Path | None, *, flush_every: int = 25) -> None:
        self.path = path
        self.flush_every = max(1, int(flush_every))
        self._lock = threading.Lock()
        self._dirty = 0
        self._data: dict[str, Any] = {}
        if path and path.is_file():
            try:
                self._data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._data = {}

    def get(self, key: str) -> Any | None:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._dirty += 1
            if self._dirty >= self.flush_every:
                self._flush_unlocked()

    def flush(self) -> None:
        with self._lock:
            self._flush_unlocked()

    def _flush_unlocked(self) -> None:
        if self.path is None or self._dirty == 0:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)
        self._dirty = 0


def cache_key(
    *,
    prompt_id: str,
    model: str,
    payload: Mapping[str, Any],
) -> str:
    ph = prompt_hash(prompt_id)
    blob = json.dumps(
        {"prompt_id": prompt_id, "prompt_hash": ph, "model": model, "payload": payload},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class LexicalJudge:
    """Compatible lexical matcher (leaf_match_score). Not paper-official."""

    name = "lexical"
    protocol = "compatible_metrics_lexical_v1"
    model = "lexical"
    threshold = DEFAULT_LEXICAL_THRESHOLD

    def diagnosis_match_score(self, pred: str, gold: str) -> float:
        return float(leaf_match_score(pred, gold))

    def diagnoses_equivalent(self, pred: str, gold: str) -> bool:
        return self.diagnosis_match_score(pred, gold) >= self.threshold

    def interpretation_item_match(self, pred: str, gold: str) -> bool:
        return self.diagnosis_match_score(pred, gold) >= self.threshold

    def reasoning_point_covered(self, point: str, trace: str) -> bool:
        p = str(point or "").strip().lower()
        t = str(trace or "").strip().lower()
        if not p or not t:
            return False
        if p in t:
            return True
        # Soft token overlap
        pt = set(re.findall(r"[a-z0-9]+", p))
        tt = set(re.findall(r"[a-z0-9]+", t))
        if len(pt) < 3:
            return False
        inter = len(pt & tt)
        return inter >= max(3, int(0.6 * len(pt)))


class LLMJudge:
    """Paper-aligned prompts; default model Gemini 2.5 Flash."""

    name = "llm"
    protocol = "paper_aligned_judge_v1"
    model = JUDGE_MODEL_SLUG
    model_short = JUDGE_MODEL_SHORT
    env = JUDGE_ENV
    vpn = JUDGE_VPN
    workers = JUDGE_WORKERS

    def __init__(
        self,
        *,
        client: Any | None = None,
        cache: JudgeCache | None = None,
        temperature: float = 0.0,
        model: str | None = None,
    ) -> None:
        self.client = client
        self.cache = cache or JudgeCache(None)
        self.temperature = temperature
        if model:
            self.model = str(model)
            # Short name = last path segment
            self.model_short = self.model.rsplit("/", 1)[-1]
        self._templates: dict[str, tuple[str, str]] = {}

    def _template(self, prompt_id: str) -> str:
        if prompt_id not in self._templates:
            self._templates[prompt_id] = load_prompt_template(prompt_id)
        return self._templates[prompt_id][0]

    def _complete(self, prompt_id: str, filled: str, payload: Mapping[str, Any]) -> str:
        key = cache_key(prompt_id=prompt_id, model=self.model, payload=dict(payload))
        hit = self.cache.get(key)
        if isinstance(hit, Mapping) and "text" in hit:
            cached = str(hit["text"])
            if not cached.startswith("[Unable to generate"):
                return cached
        if self.client is None:
            raise RuntimeError(
                "LLM judge cache miss and no client; activate gnn-llm + clashon "
                "and pass RobustLLMClient(model=%r)" % self.model
            )
        messages = [{"role": "user", "content": filled}]
        # Prompt 7 / Appendix 3 often return a single token: y/n or 0/1.
        # RobustLLMClient default min_response_length=10 would reject these and
        # retry up to max_retries (noisy + slow under concurrency).
        text = self.client.get_robust_completion(
            messages,
            description="judge:%s" % prompt_id,
            temperature=self.temperature,
            min_length=1,
            max_retries=3,
        )
        text = str(text or "")
        if text.startswith("[Unable to generate"):
            # An exhausted-retry sentinel parses to an empty verdict and would be
            # scored as zero coverage. Fail the case instead of caching a score
            # that reflects a transport failure rather than the judge's reading.
            raise RuntimeError(
                "judge call failed after retries (%s): %s" % (prompt_id, text)
            )
        self.cache.set(key, {"text": text, "prompt_id": prompt_id})
        return text

    def diagnoses_equivalent(self, pred: str, gold: str) -> bool:
        tmpl = self._template("ox.ddx_match")
        filled = tmpl.replace("{key_pred}", pred).replace("{key_gnd}", gold)
        raw = self._complete(
            "ox.ddx_match",
            filled,
            {"key_pred": pred, "key_gnd": gold},
        )
        bit = parse_ox_bit(raw)
        return bit == 1

    def diagnosis_match_score(self, pred: str, gold: str) -> float:
        return 1.0 if self.diagnoses_equivalent(pred, gold) else 0.0

    def interpretation_item_match(self, pred: str, gold: str) -> bool:
        tmpl = self._template("ox.interpretation_consistency")
        filled = tmpl.replace("{reason_i}", gold).replace("{reason_j}", pred)
        raw = self._complete(
            "ox.interpretation_consistency",
            filled,
            {"reason_i": gold, "reason_j": pred},
        )
        bit = parse_ox_bit(raw)
        return bit == 1

    def mcr_diagnosis_correct(self, pred: str, gold: str) -> bool:
        tmpl = self._template("mcr.diag_accuracy")
        filled = (
            tmpl.replace("{predicted_diagnosis}", pred)
            .replace("{actual_diagnosis}", gold)
        )
        raw = self._complete(
            "mcr.diag_accuracy",
            filled,
            {"predicted_diagnosis": pred, "actual_diagnosis": gold},
        )
        yn = parse_yn(raw)
        return bool(yn)

    def reasoning_recall_coverage(
        self,
        gold_points: list[str],
        pred_trace: str,
    ) -> tuple[float, dict[str, list[str]]]:
        tmpl = self._template("mcr.reasoning_recall")
        gt_lines = "\n".join(
            "%d. %s" % (i + 1, p) for i, p in enumerate(gold_points)
        )
        # Trace may already be multi-line; present as Predicted Diagnostic Reasons
        user = (
            tmpl
            + "\n\nGroundtruth Diagnostic Reasons:\n"
            + gt_lines
            + "\n\nPredicted Diagnostic Reasons:\n"
            + str(pred_trace or "").strip()
        )
        raw = self._complete(
            "mcr.reasoning_recall",
            user,
            {"n_gold": len(gold_points), "trace_hash": hashlib.sha256(
                str(pred_trace).encode("utf-8")
            ).hexdigest()[:16]},
        )
        md = parse_reasoning_matching_dict(raw)
        covered = 0
        for i in range(len(gold_points)):
            hits = md.get(str(i + 1)) or md.get(str(i)) or []
            if hits:
                covered += 1
        recall = (covered / len(gold_points)) if gold_points else 0.0
        return recall, md


def make_judge(
    kind: str,
    *,
    cache_path: Path | None = None,
    client: Any | None = None,
) -> LexicalJudge | LLMJudge:
    k = str(kind or "lexical").strip().lower()
    if k == "lexical":
        return LexicalJudge()
    if k == "llm":
        return LLMJudge(client=client, cache=JudgeCache(cache_path))
    raise ValueError("unknown judge: %s" % kind)
