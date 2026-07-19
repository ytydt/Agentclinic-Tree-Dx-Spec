"""Micro-benchmark: multi-GPU EncoderPool vs single-GPU + global lock.

Spawns T worker threads each issuing N encode() calls and measures wall-clock
throughput, to verify de-serialization across GPUs actually parallelizes.

Usage:
  TREE_DX_EMBED_DEVICES=cuda:0,cuda:1,cuda:2 python scripts/bench_encoder_pool.py
  TREE_DX_EMBED_DEVICES= TREE_DX_EMBED_DEVICE=cuda:0 python scripts/bench_encoder_pool.py
"""
from __future__ import annotations

import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

_alloc = os.environ.get("PYTORCH_CUDA_ALLOC_CONF", "")
if "max_split_size_mb:" in _alloc:
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = ""

from agentclinic_tree_dx.knowledge import embedding_index as ei  # noqa: E402

THREADS = int(os.environ.get("BENCH_THREADS", "9"))
PER_THREAD = int(os.environ.get("BENCH_N", "40"))
TEXTS = [
    "necrolytic migratory erythema in glucagonoma",
    "unilateral bloody nasal discharge in a child",
    "massive leukocytosis with basophilia and splenomegaly",
    "right upper quadrant pain with anabolic steroid use",
]


def main() -> int:
    pool = ei._get_pool()
    mode = f"POOL size={pool.size} devices={pool._devices}" if pool else "SINGLE (lock)"
    model = ei._get_model()
    if model is None:
        print("model unavailable")
        return 1
    # warm up (load all replicas / single model)
    ei._encode(model, TEXTS, normalize_embeddings=True, show_progress_bar=False)

    def worker(wid: int) -> int:
        for i in range(PER_THREAD):
            ei._encode(model, [TEXTS[(wid + i) % len(TEXTS)]],
                       normalize_embeddings=True, show_progress_bar=False)
        return PER_THREAD

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=THREADS) as ex:
        total = sum(ex.map(worker, range(THREADS)))
    dt = time.time() - t0
    print(f"mode={mode}")
    print(f"threads={THREADS} per_thread={PER_THREAD} total_encodes={total}")
    print(f"wall={dt:.2f}s  throughput={total/dt:.1f} encodes/s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
