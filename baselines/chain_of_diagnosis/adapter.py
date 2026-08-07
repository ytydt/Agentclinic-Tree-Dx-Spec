"""Chain-of-Diagnosis / DiagnosisGPT adapter.

- B11a: local GPU DiagnosisGPT weights (official disease DB + CoD chain).
- B11b: same-backbone CoD five-step prompt + shared rag_index/cpg_index.

Set ``baselines/chain_of_diagnosis/READY`` after weights are installed.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

UPSTREAM_URL = "https://github.com/FreedomIntelligence/Chain-of-Diagnosis"
HF_6B = "FreedomIntelligence/DiagnosisGPT-6B"
HF_34B = "FreedomIntelligence/DiagnosisGPT-34B"
DISEASE_DB = "FreedomIntelligence/Disease_Database"

ROOT = Path(__file__).resolve().parents[2]
VENDOR_DIR = Path(__file__).resolve().parent
UPSTREAM_DIR = VENDOR_DIR / "upstream"
DEFAULT_MODEL_DIR = VENDOR_DIR / "models" / "DiagnosisGPT-6B"
READY_MARKER = VENDOR_DIR / "READY"

_BOT: Any = None
_MODEL_DIR: str | None = None


def is_ready(model_dir: Path | None = None) -> bool:
    path = Path(model_dir or os.environ.get("B11A_MODEL_DIR") or DEFAULT_MODEL_DIR)
    return READY_MARKER.is_file() and path.is_dir() and (path / "config.json").is_file()


def _ensure_upstream_on_path() -> None:
    text = str(UPSTREAM_DIR)
    if text not in sys.path:
        sys.path.insert(0, text)


def load_bot(
    model_dir: Path | str | None = None,
    *,
    confidence_threshold: float = 0.5,
    force_reload: bool = False,
) -> Any:
    """Load DiagnosisChatbot once per process (CUDA_VISIBLE_DEVICES selects GPU)."""
    global _BOT, _MODEL_DIR
    path = str(Path(model_dir or os.environ.get("B11A_MODEL_DIR") or DEFAULT_MODEL_DIR))
    if _BOT is not None and _MODEL_DIR == path and not force_reload:
        return _BOT
    if not Path(path).is_dir():
        raise FileNotFoundError(f"DiagnosisGPT weights missing: {path}")
    # Guard against inherited invalid allocator conf (must be >20).
    conf = os.environ.get("PYTORCH_CUDA_ALLOC_CONF", "")
    if "max_split_size_mb" in conf:
        os.environ.pop("PYTORCH_CUDA_ALLOC_CONF", None)
    _ensure_upstream_on_path()
    from cod_cli import DiagnosisChatbot  # noqa: WPS433

    t0 = time.time()
    _BOT = DiagnosisChatbot(path, confidence_threshold=confidence_threshold)
    _MODEL_DIR = path
    load_s = time.time() - t0
    print(
        f"[B11a] loaded DiagnosisGPT pid={os.getpid()} "
        f"cuda={os.environ.get('CUDA_VISIBLE_DEVICES')} "
        f"model={path} load_s={load_s:.1f}",
        flush=True,
    )
    return _BOT


def _top2_from_confidence(conf: Mapping[str, Any]) -> list[str]:
    if not conf:
        return ["", ""]
    ordered = sorted(
        ((str(k).strip(), float(v)) for k, v in conf.items() if str(k).strip()),
        key=lambda item: -item[1],
    )
    names = [name for name, _ in ordered[:2]]
    while len(names) < 2:
        names.append("")
    return names[:2]


def _top2_from_text(text: str) -> list[str]:
    # Prefer "## Diagnosis:" / "## 做出诊断:" section.
    for marker in ("## Diagnosis:", "## 做出诊断:"):
        if marker in text:
            section = text.split(marker, 1)[1].strip()
            line = section.splitlines()[0].strip().strip('"').strip()
            if line:
                return [line, ""]
    # Candidate list bullets: - "Disease"
    candidates = re.findall(r'-\s*"([^"]+)"', text)
    if candidates:
        names: list[str] = []
        for name in candidates:
            if name not in names:
                names.append(name)
            if len(names) >= 2:
                break
        while len(names) < 2:
            names.append("")
        return names[:2]
    # Free-form fallbacks when CoD confidence block is absent.
    patterns = [
        r"(?:suffering from|known as|diagnosis(?: is| of)?|presenting with)\s+"
        r"(?:a condition known as\s+|cutaneous\s+)?([A-Z][^.\n]{2,100}?)(?:\.|,| which| that|,\s*which)",
        r"(?:患有|诊断为|可能患有)[：:\s]*([^\n。，,]{2,80})",
    ]
    found: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            name = match.group(1).strip().strip('"').strip()
            name = re.sub(r"\s+", " ", name)
            if name and name.casefold() not in {x.casefold() for x in found}:
                found.append(name)
            if len(found) >= 2:
                return found[:2]
    if found:
        while len(found) < 2:
            found.append("")
        return found[:2]
    return ["", ""]


def _quoted_phrases(text: str) -> list[str]:
    phrases: list[str] = []
    for item in re.findall(r'"([^"]{2,160})"', text or ""):
        name = item.strip()
        if name and name.casefold() not in {p.casefold() for p in phrases}:
            phrases.append(name)
    return phrases


def _continue_cod_from_symptoms(
    bot: Any,
    *,
    query: str,
    partial_output: str,
    true_syms: Sequence[str],
    false_syms: Sequence[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Finish CoD when the model emitted symptoms but skipped the banner path."""
    false_syms = list(false_syms or [])
    true_syms = [str(x).strip() for x in true_syms if str(x).strip()]
    if not true_syms:
        return partial_output, {}
    candi = bot.retriever_en.find_top_k(true_syms, false_syms)
    t2_str = bot.get_candidate_dis(candi, is_en=True)
    prompt = bot.generate_prompt(query, [])
    # Upstream expects the symptom-analysis banner before candidates.
    banner = "Enter the diagnostic process, analyzing patient symptoms:\n"
    cur = banner + partial_output
    if not cur.endswith("\n"):
        cur += "\n"
    cur += t2_str
    generated = bot.model_genrate(prompt + cur)
    conf: dict[str, Any] = {}
    try:
        match = re.search(r"## Diagnostic confidence:\s*(.*)", generated, re.DOTALL)
        if match:
            conf = json.loads(match.group(1))
    except Exception:  # noqa: BLE001
        conf = {}
    cur += generated
    if conf:
        max_key = max(conf, key=conf.get)
        if float(conf[max_key]) > float(bot.confidence_threshold):
            cur += "\n\n## Diagnosis:\n"
            cur += bot.model_genrate(prompt + cur)
    return cur, conf if isinstance(conf, dict) else {}


def diagnose_case(
    vignette: str,
    *,
    model_dir: Path | str | None = None,
    confidence_threshold: float = 0.5,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    """Run official DiagnosisGPT CoD inference; return Top-2 + trace + cost."""
    bot = load_bot(model_dir, confidence_threshold=confidence_threshold)
    # Static complete case: present vignette as patient utterance and request CoD.
    query = (
        "I am a patient with the following complete clinical information "
        "(no further questions will be answered):\n"
        f"{vignette.strip()}\n\n"
        "Please enter the diagnostic process, analyzing patient symptoms."
    )
    t0 = time.time()
    result = bot.inference(query, history=[])
    if isinstance(result, tuple) and len(result) == 3:
        output, history, confidence = result
    else:
        output, history, confidence = result, [], {}
    conf = confidence if isinstance(confidence, Mapping) else {}
    continued = False
    if not conf:
        # Recovery: model often emits quoted symptoms without CoD banner.
        true_syms = _quoted_phrases(str(output or ""))
        false_syms = re.findall(r'(?:No|没有)\s*"([^"]+)"', str(output or ""))
        if true_syms:
            output, conf = _continue_cod_from_symptoms(
                bot,
                query=query,
                partial_output=str(output or ""),
                true_syms=true_syms,
                false_syms=false_syms,
            )
            continued = True
            history = [(query, output)]
    latency = time.time() - t0
    conf = conf if isinstance(conf, Mapping) else {}
    top2 = _top2_from_confidence(conf)
    if not any(top2):
        # Prefer disease candidates from English candidate block.
        cand = re.findall(r'-\s*"([^"]+)"', str(output or ""))
        if cand:
            top2 = (cand + ["", ""])[:2]
        else:
            top2 = _top2_from_text(str(output or ""))
    cost = {
        "llm_calls": 2 if continued else 1,
        "input_tokens_est": 0,
        "output_tokens_est": 0,
        "retrieval_calls": 1 if (conf or continued) else 0,
        "retrieval_snippets": len(conf),
        "snippet_chars": 0,
        "latency_s": latency,
    }
    trace = {
        "status": "ok",
        "model_dir": _MODEL_DIR,
        "worker_pid": os.getpid(),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "confidence": dict(conf),
        "output_tail": str(output or "")[-2000:],
        "history_turns": len(history or []),
        "entered_cod": bool(conf),
        "cod_continued": continued,
    }
    return top2, trace, cost


def mark_ready(model_dir: Path | None = None) -> Path:
    path = Path(model_dir or DEFAULT_MODEL_DIR)
    if not (path / "config.json").is_file():
        raise FileNotFoundError(f"cannot mark READY; missing config.json under {path}")
    READY_MARKER.write_text(
        json.dumps(
            {
                "model_dir": str(path),
                "hf_id": HF_6B,
                "upstream": UPSTREAM_URL,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return READY_MARKER
