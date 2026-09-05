#!/usr/bin/env python3
"""Fine-tune MedCPT-Cross-Encoder as a relation-slot verifier (§16.8).

Pair task: (guideline evidence, verbalised assertion) -> is this relation slot
licensed by the text?  Train on ten cases with the F7 gate as teacher plus
controlled perturbations; test on case 74's human census, which the model has
never seen.

Baselines reported next to it:

- **F7 gates**: their own row-level keep/demote call.  Note this baseline is
  optimistically biased -- the regexes were written *after* reading the same
  case-74 census that provides the test labels.
- **zero-shot MedCPT**: the pretrained relevance head, ranked against the
  labels (AUC only; its score is not a licensing decision).
- **majority class**: always "not licensed".
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import (AutoConfig, AutoModelForSequenceClassification,
                          AutoTokenizer, get_linear_schedule_with_warmup)

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
DATA = LEDGER / "relation_verifier"
MODEL = "ncbi/MedCPT-Cross-Encoder"


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text("utf-8").splitlines() if l.strip()]


class PairSet(Dataset):
    def __init__(self, rows: list[dict], tok, max_len: int, field: str = "evidence"):
        self.rows, self.tok, self.max_len = rows, tok, max_len
        self.field = field

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, i: int) -> dict:
        r = self.rows[i]
        enc = self.tok(r.get(self.field) or r["evidence"], r["statement"],
                       truncation=True,
                       max_length=self.max_len, padding="max_length",
                       return_tensors="pt")
        item = {k: v.squeeze(0) for k, v in enc.items()}
        item["labels"] = torch.tensor(int(r["label"]))
        return item


def prf(pred: list[int], gold: list[int]) -> dict:
    tp = sum(p == 1 and g == 1 for p, g in zip(pred, gold))
    fp = sum(p == 1 and g == 0 for p, g in zip(pred, gold))
    fn = sum(p == 0 and g == 1 for p, g in zip(pred, gold))
    tn = sum(p == 0 and g == 0 for p, g in zip(pred, gold))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    prec0 = tn / (tn + fn) if tn + fn else 0.0
    rec0 = tn / (tn + fp) if tn + fp else 0.0
    f10 = 2 * prec0 * rec0 / (prec0 + rec0) if prec0 + rec0 else 0.0
    return {
        "acc": (tp + tn) / max(1, len(gold)),
        "licensed_P": prec, "licensed_R": rec, "licensed_F1": f1,
        "macro_F1": (f1 + f10) / 2,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


# F7 only ever targets the diagnostic slots; the 134 ``excludes`` rows are
# relation errors it passes through by design (§14.4).  Scoring on all 225 rows
# alone would misread that as a failure, so every system is scored on three
# nested row sets.
SUBSETS = {
    "all_225": lambda r: True,
    "diagnostic_91": lambda r: r["relation"] in {
        "required_for", "pathognomonic_for", "sufficient_for"},
    "required_57": lambda r: r["relation"] == "required_for",
}


def by_subset(pred: list[int], rows: list[dict]) -> dict:
    out = {}
    for name, keep in SUBSETS.items():
        idx = [i for i, r in enumerate(rows) if keep(r)]
        out[name] = prf([pred[i] for i in idx], [rows[i]["label"] for i in idx])
        out[name]["n"] = len(idx)
    return out


def auc(score: list[float], gold: list[int]) -> float:
    pos = [s for s, g in zip(score, gold) if g == 1]
    neg = [s for s, g in zip(score, gold) if g == 0]
    if not pos or not neg:
        return float("nan")
    order = sorted(range(len(score)), key=lambda i: score[i])
    rank = {}
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and score[order[j + 1]] == score[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            rank[order[k]] = avg
        i = j + 1
    rsum = sum(rank[i] for i in range(len(score)) if gold[i] == 1)
    return (rsum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def threshold_study(scores: list[float], rows: list[dict],
                    ks=(20, 40, 80), draws: int = 200, seed: int = 0) -> dict:
    """How many *human* labels does the decision threshold actually need?

    The encoder ranks well but the operating point does not transfer from
    teacher-labelled dev data.  Picking the threshold on k annotated rows of the
    target case and scoring the rest bounds the annotation budget.
    """
    gold = [r["label"] for r in rows]
    grid = list(np.arange(0.02, 0.99, 0.02))

    def best_thr(idx: list[int]) -> float:
        g = [gold[i] for i in idx]
        s = [scores[i] for i in idx]
        return max(grid, key=lambda t: prf([int(x > t) for x in s], g)["macro_F1"])

    out = {"oracle": prf([int(s > best_thr(list(range(len(rows))))) for s in scores],
                         gold)["macro_F1"]}
    rng = random.Random(seed)
    for k in ks:
        vals = []
        for _ in range(draws):
            idx = rng.sample(range(len(rows)), k)
            rest = [i for i in range(len(rows)) if i not in set(idx)]
            t = best_thr(idx)
            vals.append(prf([int(scores[i] > t) for i in rest],
                            [gold[i] for i in rest])["macro_F1"])
        out[f"k={k}"] = {"mean": float(np.mean(vals)), "sd": float(np.std(vals))}
    return out


@torch.no_grad()
def infer(model, loader, device) -> tuple[list[int], list[float]]:
    model.eval()
    preds, scores = [], []
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items() if k != "labels"}
        with torch.autocast("cuda", dtype=torch.bfloat16):
            logits = model(**batch).logits.float()
        if logits.shape[-1] == 1:
            s = logits.squeeze(-1)
            preds += [0] * len(s)
        else:
            p = logits.softmax(-1)[:, 1]
            s = p
            preds += (p > 0.5).long().tolist()
        scores += s.tolist()
    return preds, scores


def run_seed(seed: int, train_rows: list[dict], dev_rows: list[dict],
             test_rows: list[dict], args, device) -> dict:
    torch.manual_seed(seed)
    random.seed(seed)
    np.random.seed(seed)

    tok = AutoTokenizer.from_pretrained(MODEL)
    # MedCPT ships a 1-logit ranking head; swap it for a fresh 2-way classifier
    # and keep the encoder.  (``num_labels`` at load time is absorbed into the
    # config and the mismatch flag gets dropped, hence the explicit surgery.)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL)
    model.classifier = torch.nn.Linear(model.config.hidden_size, 2)
    model.num_labels = 2
    model.config.num_labels = 2
    model.config.problem_type = "single_label_classification"
    model = model.to(device)

    tr = DataLoader(PairSet(train_rows, tok, args.max_len, args.evidence), batch_size=args.bs,
                    shuffle=True, num_workers=2, drop_last=False)
    dv = DataLoader(PairSet(dev_rows, tok, args.max_len, args.evidence), batch_size=64)
    te = DataLoader(PairSet(test_rows, tok, args.max_len, args.evidence), batch_size=64)

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    total = len(tr) * args.epochs
    sch = get_linear_schedule_with_warmup(opt, int(0.1 * total), total)

    best = None
    for ep in range(args.epochs):
        model.train()
        run = 0.0
        for step, batch in enumerate(tr):
            batch = {k: v.to(device) for k, v in batch.items()}
            with torch.autocast("cuda", dtype=torch.bfloat16):
                out = model(**batch)
            out.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sch.step()
            opt.zero_grad()
            run += out.loss.item()
        dp, ds_ = infer(model, dv, device)
        dm = prf(dp, [r["label"] for r in dev_rows])
        # The test prior is far below the training prior, so the decision
        # threshold is picked on dev rather than left at 0.5.
        dev_gold = [r["label"] for r in dev_rows]
        thr, best_dev = 0.5, dm["macro_F1"]
        for cand in np.arange(0.05, 0.96, 0.05):
            mf = prf([int(s > cand) for s in ds_], dev_gold)["macro_F1"]
            if mf > best_dev:
                thr, best_dev = float(cand), mf
        print(f"    seed{seed} ep{ep + 1} loss={run / max(1, len(tr)):.4f} "
              f"dev_macroF1={dm['macro_F1']:.3f} thr={thr:.2f}", flush=True)
        _, ts_ = infer(model, te, device)
        tp_ = [int(s > thr) for s in ts_]
        tm = prf(tp_, [r["label"] for r in test_rows])
        tm["threshold"] = thr
        tm["subsets"] = by_subset(tp_, test_rows)
        tm["dev_macro_F1"] = dm["macro_F1"]
        tm["epoch"] = ep + 1
        tm["auc"] = auc(ts_, [r["label"] for r in test_rows])
        if best is None or dm["macro_F1"] > best["dev_macro_F1"]:
            best = tm
            best["pred"] = tp_
            best["score"] = ts_
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--bs", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--max_len", type=int, default=384)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--train_file", type=str, default="train_other10.jsonl")
    ap.add_argument("--tag", type=str, default="teacher")
    ap.add_argument("--evidence", choices=["evidence", "evidence_sentence"],
                    default="evidence")
    ap.add_argument("--dev_cases", type=str, nargs="+", default=["49", "119"])
    args = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"

    train_all = load(DATA / args.train_file)
    test_rows = load(DATA / "test_case74.jsonl")
    dev_rows = [r for r in train_all if r["case"] in set(args.dev_cases)]
    train_rows = [r for r in train_all if r["case"] not in set(args.dev_cases)]
    gold = [r["label"] for r in test_rows]

    print(f"train={len(train_rows)} (cases "
          f"{sorted({r['case'] for r in train_rows})})", flush=True)
    print(f"dev={len(dev_rows)} (cases {args.dev_cases})  test={len(test_rows)} "
          f"(case 74, licensed={sum(gold)})", flush=True)

    print("\n=== baselines on case 74 ===", flush=True)
    maj = prf([0] * len(gold), gold)
    maj["subsets"] = by_subset([0] * len(gold), test_rows)
    f7 = prf([r["f7_pred"] for r in test_rows], gold)
    f7["subsets"] = by_subset([r["f7_pred"] for r in test_rows], test_rows)
    for name in SUBSETS:
        m, f = maj["subsets"][name], f7["subsets"][name]
        print(f"  {name:<14} n={m['n']:>3}  majority acc={m['acc']:.3f} "
              f"macroF1={m['macro_F1']:.3f} | F7 acc={f['acc']:.3f} "
              f"macroF1={f['macro_F1']:.3f} licP/R="
              f"{f['licensed_P']:.2f}/{f['licensed_R']:.2f}", flush=True)

    tok = AutoTokenizer.from_pretrained(MODEL)
    zs = AutoModelForSequenceClassification.from_pretrained(MODEL).to(device)
    te = DataLoader(PairSet(test_rows, tok, args.max_len, args.evidence), batch_size=64)
    _, zs_scores = infer(zs, te, device)
    zs_auc = auc(zs_scores, gold)
    print(f"  zero-shot MedCPT relevance AUC={zs_auc:.3f}", flush=True)
    del zs
    torch.cuda.empty_cache()

    print("\n=== fine-tuning MedCPT-Cross-Encoder ===", flush=True)
    runs = []
    for s in args.seeds:
        runs.append(run_seed(s, train_rows, dev_rows, test_rows, args, device))
        r = runs[-1]
        print(f"  seed{s}: acc={r['acc']:.3f} macroF1={r['macro_F1']:.3f} "
              f"licensed P/R/F1={r['licensed_P']:.2f}/{r['licensed_R']:.2f}/"
              f"{r['licensed_F1']:.2f} AUC={r['auc']:.3f} (ep{r['epoch']})",
              flush=True)

    def agg(key: str) -> tuple[float, float]:
        v = [r[key] for r in runs]
        return float(np.mean(v)), float(np.std(v))

    print("\n=== summary on case 74 (human labels) ===", flush=True)
    print(f"  {'system':<34}{'acc':>7}{'macroF1':>9}{'licF1':>8}{'AUC':>8}",
          flush=True)
    print(f"  {'majority':<34}{maj['acc']:>7.3f}{maj['macro_F1']:>9.3f}"
          f"{maj['licensed_F1']:>8.3f}{'-':>8}", flush=True)
    print(f"  {'F7 regex gates (biased)':<34}{f7['acc']:>7.3f}"
          f"{f7['macro_F1']:>9.3f}{f7['licensed_F1']:>8.3f}{'-':>8}", flush=True)
    print(f"  {'MedCPT zero-shot':<34}{'-':>7}{'-':>9}{'-':>8}{zs_auc:>8.3f}",
          flush=True)
    m_acc, s_acc = agg("acc")
    m_mf, s_mf = agg("macro_F1")
    m_lf, s_lf = agg("licensed_F1")
    m_au, s_au = agg("auc")
    print(f"  {'MedCPT fine-tuned (n=%d seeds)' % len(runs):<34}{m_acc:>7.3f}"
          f"{m_mf:>9.3f}{m_lf:>8.3f}{m_au:>8.3f}", flush=True)
    print(f"  {'  (sd)':<34}{s_acc:>7.3f}{s_mf:>9.3f}{s_lf:>8.3f}{s_au:>8.3f}",
          flush=True)

    print("\n=== per row-set macro-F1 (mean over seeds) ===", flush=True)
    print(f"  {'row set':<16}{'n':>5}{'majority':>10}{'F7':>8}{'MedCPT':>9}",
          flush=True)
    for name in SUBSETS:
        ft = float(np.mean([r["subsets"][name]["macro_F1"] for r in runs]))
        print(f"  {name:<16}{maj['subsets'][name]['n']:>5}"
              f"{maj['subsets'][name]['macro_F1']:>10.3f}"
              f"{f7['subsets'][name]['macro_F1']:>8.3f}{ft:>9.3f}", flush=True)

    best = max(runs, key=lambda r: r["dev_macro_F1"])

    print("\n=== AUC by row set (mean over seeds) ===", flush=True)
    subset_auc = {}
    for name, keep in SUBSETS.items():
        idx = [i for i, r in enumerate(test_rows) if keep(r)]
        a = [auc([r["score"][i] for i in idx], [test_rows[i]["label"] for i in idx])
             for r in runs]
        subset_auc[name] = float(np.mean(a))
        print(f"  {name:<16} n={len(idx):>3}  AUC={np.mean(a):.3f}", flush=True)

    print("\n=== how many human labels does the threshold need? ===", flush=True)
    study = threshold_study(best["score"], test_rows)
    print(f"  oracle threshold (all 225 labelled): macroF1={study['oracle']:.3f}",
          flush=True)
    for k in [k for k in study if k.startswith("k=")]:
        print(f"  threshold from {k:<6} labelled rows: "
              f"macroF1={study[k]['mean']:.3f} (sd {study[k]['sd']:.3f})",
              flush=True)
    out = {
        "test": "case74 human census (225 rows, %d licensed)" % sum(gold),
        "note": "F7 baseline is optimistically biased: its regexes were written "
                "after reading this census. The model never saw case 74.",
        "majority": maj, "f7": f7, "zero_shot_auc": zs_auc,
        "finetuned_mean": {"acc": m_acc, "macro_F1": m_mf,
                           "licensed_F1": m_lf, "auc": m_au},
        "finetuned_sd": {"acc": s_acc, "macro_F1": s_mf,
                         "licensed_F1": s_lf, "auc": s_au},
        "per_seed": [{k: v for k, v in r.items()
                      if k not in {"pred", "score"}} for r in runs],
        "subset_auc": subset_auc,
        "threshold_study": study,
        "best_seed_scores": best["score"],
        "disagreements": [
            {"quote": t["quote"], "relation": t["relation"],
             "subject": t["subject"], "predicate": t["predicate"],
             "gold": t["label"], "f7": t["f7_pred"], "medcpt": p}
            for t, p in zip(test_rows, best["pred"])
            if p != t["f7_pred"]
        ],
    }
    (DATA / f"verifier_results_{args.tag}.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {DATA}/verifier_results_{args.tag}.json "
          f"({len(out['disagreements'])} rows where MedCPT and F7 differ)",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
