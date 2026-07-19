"""Secondary (tier-2) LR cache for RAG-derived likelihood ratios.

The primary unified cache (``unified_symptom_disease_cache.json``) is a curated,
build-time artifact and must stay clean. RAG-time quantification (see
:mod:`knowledge.lr_quant`) produces lower-confidence numeric LRs for cache
misses; persisting those into a SEPARATE secondary cache lets repeated
runs/cases reuse the (expensive) RAG computation without polluting the primary
cache and without re-running embedding search + extraction every time.

Design:
  - keyed by ``"{finding}::{disease}"`` (lowercased, original surface forms);
  - stores the computed entry, OR a null marker when RAG produced no usable
    quantitative signal (so we don't re-attempt a known dead end);
  - thread-safe within a process (the eval shares one retriever across worker
    threads);
  - §30 cross-PROCESS safe write-back: the eval runs MANY processes concurrently
    (1/GPU + N/CPU), all pointing at the SAME cache file. The previous fixed
    ``.tmp`` name made ``os.replace`` race (process A's replace deleted the tmp
    that process B was about to move → ENOENT "flush failed" warnings) AND
    silently dropped entries (last writer clobbered the others). The fix:
      * unique per-process ``.tmp`` name (pid+uuid) → no tmp collision;
      * an ``fcntl.flock`` exclusive lock around RE-READ → MERGE → atomic
        replace, so concurrent flushes never lose each other's writes.
  - §30 READ-ONLY mode for offline-built artifacts (``*.clean.json`` /
    ``*.detox.json``): these are deterministic offline products and must NOT be
    written back by concurrent eval (that both races and would let one arm's
    live-RAG entries leak into a curated file). In read-only mode ``put`` only
    updates the in-memory copy and ``flush`` is a no-op.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Optional

try:
    import fcntl  # POSIX only; the eval host is Linux
    _HAVE_FCNTL = True
except Exception:  # pragma: no cover - non-POSIX fallback
    _HAVE_FCNTL = False

logger = logging.getLogger(__name__)

# Offline-built, curated artifacts that concurrent eval must never write back.
_READONLY_SUFFIXES = (".clean.json", ".detox.json")


class SecondaryLRCache:
    def __init__(self, path: str | Path, flush_every: int = 25,
                 read_only: Optional[bool] = None) -> None:
        self.path = Path(path)
        self._flush_every = max(1, flush_every)
        self._lock = threading.Lock()
        self._data: dict[str, Optional[dict]] = {}
        self._dirty = 0
        # auto read-only for offline-built artifacts unless explicitly overridden
        name = self.path.name
        auto_ro = any(name.endswith(sfx) for sfx in _READONLY_SUFFIXES)
        self.read_only = auto_ro if read_only is None else bool(read_only)
        self._lockfile = self.path.with_suffix(self.path.suffix + ".lock")
        self._load()
        if self.read_only:
            logger.info("SecondaryLRCache: READ-ONLY (%s) — no write-back", self.path.name)

    @staticmethod
    def _key(finding: str, disease: str) -> str:
        return f"{(finding or '').strip().lower()}::{(disease or '').strip().lower()}"

    def _load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info("SecondaryLRCache: loaded %d entries from %s",
                            len(self._data), self.path)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("SecondaryLRCache load failed (%s); starting empty", e)
                self._data = {}

    def contains(self, finding: str, disease: str) -> bool:
        return self._key(finding, disease) in self._data

    def get(self, finding: str, disease: str) -> Optional[dict]:
        """Return the stored entry. None means either 'not present' or
        'present but no signal'; use :meth:`contains` to distinguish."""
        return self._data.get(self._key(finding, disease))

    def put(self, finding: str, disease: str, entry: Optional[dict]) -> None:
        with self._lock:
            self._data[self._key(finding, disease)] = entry
            if self.read_only:
                return  # in-memory only; never persisted
            self._dirty += 1
            if self._dirty >= self._flush_every:
                self._flush_locked()

    def flush(self) -> None:
        if self.read_only:
            return
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if self.read_only:
            return
        if self._dirty == 0 and self.path.exists():
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # §30: serialize cross-process merge+replace under an flock so
            # concurrent eval processes never clobber each other's new entries.
            lock_fd = None
            if _HAVE_FCNTL:
                lock_fd = os.open(self._lockfile, os.O_CREAT | os.O_RDWR, 0o644)
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                # re-read the on-disk file and MERGE under the lock; our in-memory
                # entries win for keys we touched, on-disk wins for keys we never saw.
                merged: dict = {}
                if self.path.exists():
                    try:
                        with open(self.path, encoding="utf-8") as f:
                            merged = json.load(f)
                    except Exception:
                        merged = {}
                merged.update(self._data)
                self._data = merged
                tmp = self.path.with_suffix(
                    self.path.suffix + f".{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=0)
                os.replace(tmp, self.path)
                self._dirty = 0
            finally:
                if lock_fd is not None:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                    os.close(lock_fd)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("SecondaryLRCache flush failed: %s", e)

    def __len__(self) -> int:
        return len(self._data)
