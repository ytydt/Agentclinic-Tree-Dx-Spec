"""Live MCR400 DCI run using parent MedCPT + parent OpenRouter keys.

Does not write secrets to disk. Example:

  PYTHONPATH=. python -m src.run_mcr --limit 1
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from src.data import MCR400Dataset
from src.embed import active_mode, configure_embedding
from src.evaluate import evaluate_cases
from src.llm import OpenAICompatLLM, load_parent_openrouter_keys
from src.model import ECRAgent, ModelConfig
from src.utils import load_yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/base.yaml")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--parent", default="..")
    parser.add_argument("--no-live-search", action="store_true")
    args = parser.parse_args()

    cfg_path = Path(args.config)
    raw = load_yaml(cfg_path) if cfg_path.is_file() else {}
    model_cfg = raw.get("model") or {}
    llm_cfg = raw.get("llm") or {}
    parent = Path(args.parent).resolve()

    keys = load_parent_openrouter_keys(parent)
    if not keys["OPENROUTER_API_KEY"] and not keys["OPENROUTER_API_KEY2"]:
        raise SystemExit("no OpenRouter key from env or parent llm_client.py")

    embedding = str(model_cfg.get("embedding", "medcpt"))
    configure_embedding(embedding)
    config = ModelConfig.from_mapping(
        model_cfg,
        live_search=False if args.no_live_search else None,
    )
    llm = OpenAICompatLLM(
        model=str(llm_cfg.get("base_model", "qwen/qwen3-32b")),
        temperature=float(llm_cfg.get("temperature", 0.0)),
        max_tokens=int(llm_cfg.get("max_tokens", 2048)),
        api_base=(llm_cfg.get("api_base") or None),
        parent_root=parent,
    )
    agent = ECRAgent(llm=llm, config=config)
    cases = MCR400Dataset(parent).cases[args.offset : args.offset + args.limit]

    rows = []
    def predict(x: str) -> str:
        result = agent.dci_pipeline(x)
        rows.append(
            {
                "diagnosis": result.diagnosis,
                "dset": result.dset,
                "scores": result.scores,
            }
        )
        return result.diagnosis

    report = evaluate_cases(cases, predict)
    out_dir = Path("runs")
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "created_at": stamp,
        "embedding": active_mode(),
        "model": llm.model,
        "key_source": "parent_llm_client_or_env",
        "has_key1": bool(keys["OPENROUTER_API_KEY"]),
        "has_key2": bool(keys["OPENROUTER_API_KEY2"]),
        "n": len(cases),
        "acc_base": report.acc_base,
        "acc_rob": report.acc_rob,
        "r_bias": report.r_bias,
        "unpaired": report.unpaired,
        "cases": [
            {
                "case_id": c.case_id,
                "slice": c.slice_name,
                "y_gt": c.y_gt,
                **rows[i],
            }
            for i, c in enumerate(cases)
        ],
    }
    out = out_dir / f"mcr_dci_{stamp}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("embedding", "model", "n", "acc_base", "unpaired")}, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    main()
