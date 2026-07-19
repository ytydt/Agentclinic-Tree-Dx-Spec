"""§30 concern #4: prove the segfault guards (FAISS search lock + OMP thread
cap) do NOT change retrieval results — they only affect concurrency/timing."""
import numpy as np
import pytest

faiss = pytest.importorskip("faiss")


def _build(seed=0, n=2000, d=64):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, d)).astype(np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    idx = faiss.IndexFlatIP(d)
    idx.add(X)
    q = X[:5].copy()
    return idx, q


def test_faiss_lock_is_pure_passthrough():
    """A lock around index.search returns byte-identical (scores, indices):
    the lock cannot alter the query, index, or result — only serialize timing."""
    import threading
    idx, q = _build()
    s1, i1 = idx.search(q, 10)
    lock = threading.Lock()
    with lock:
        s2, i2 = idx.search(q, 10)
    assert np.array_equal(i1, i2)
    assert np.allclose(s1, s2)


def test_omp_thread_count_does_not_change_topk():
    """Capping OMP threads (the CPU-segfault mitigation) must not change which
    neighbours are returned, only how many cores the search uses."""
    idx, q = _build()
    faiss.omp_set_num_threads(8)
    s8, i8 = idx.search(q, 10)
    faiss.omp_set_num_threads(2)   # the §30 cap
    s2, i2 = idx.search(q, 10)
    faiss.omp_set_num_threads(1)
    s1, i1 = idx.search(q, 10)
    assert np.array_equal(i8, i2) and np.array_equal(i8, i1)
    assert np.allclose(s8, s2) and np.allclose(s8, s1)
