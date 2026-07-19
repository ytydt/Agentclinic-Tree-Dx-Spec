"""§30 regression: SecondaryLRCache cross-process safety + read-only artifacts."""
import json
import os
from pathlib import Path

from agentclinic_tree_dx.knowledge.secondary_lr_cache import SecondaryLRCache


def test_readonly_auto_for_clean_detox(tmp_path):
    for name in ("rag_lr_secondary_cache.clean.json",
                 "rag_lr_secondary_cache.detox.json"):
        p = tmp_path / name
        p.write_text(json.dumps({"a::b": {"lr_positive": 1.0}}), encoding="utf-8")
        c = SecondaryLRCache(p)
        assert c.read_only is True
        c.put("x", "y", {"lr_positive": 2.0})   # in-memory only
        assert c.get("x", "y") == {"lr_positive": 2.0}
        c.flush()                                # no-op
        # on-disk file unchanged (no new key persisted)
        on_disk = json.loads(p.read_text(encoding="utf-8"))
        assert "x::y" not in on_disk


def test_writable_for_base_cache(tmp_path):
    p = tmp_path / "rag_lr_secondary_cache.json"
    c = SecondaryLRCache(p, flush_every=1)
    assert c.read_only is False
    c.put("fever", "flu", {"lr_positive": 3.0})
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    assert on_disk["fever::flu"] == {"lr_positive": 3.0}


def test_flush_merges_not_clobbers(tmp_path):
    """Two independent cache objects on the same file (simulating two processes)
    must MERGE on flush, not clobber each other's keys."""
    p = tmp_path / "rag_lr_secondary_cache.json"
    a = SecondaryLRCache(p, flush_every=100)
    b = SecondaryLRCache(p, flush_every=100)
    a.put("f1", "d1", {"lr_positive": 1.1})
    b.put("f2", "d2", {"lr_positive": 2.2})
    a.flush()
    b.flush()                       # must not drop a's f1::d1
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    assert on_disk["f1::d1"] == {"lr_positive": 1.1}
    assert on_disk["f2::d2"] == {"lr_positive": 2.2}


def test_unique_tmp_no_collision(tmp_path):
    p = tmp_path / "rag_lr_secondary_cache.json"
    c = SecondaryLRCache(p, flush_every=1)
    c.put("a", "b", {"x": 1})
    # no leftover fixed-name tmp
    assert not (tmp_path / "rag_lr_secondary_cache.json.tmp").exists()


def _proc_writer(path, pid, n):
    # each process writes n distinct keys then flushes — stresses the
    # cross-process flock-merge (production: no write lost).
    import json as _json
    from agentclinic_tree_dx.knowledge.secondary_lr_cache import SecondaryLRCache as _C
    c = _C(path, flush_every=7)
    for i in range(n):
        c.put(f"f{pid}_{i}", f"d{pid}", {"lr_positive": pid * 100 + i})
    c.flush()


def test_cross_process_writes_not_lost(tmp_path):
    """Concern #2 (production): MANY concurrent processes writing the SAME cache
    file must ALL complete with NO lost writes (flock-serialized merge)."""
    import multiprocessing as mp
    p = tmp_path / "rag_lr_secondary_cache.json"
    nproc, nkey = 6, 30
    procs = [mp.Process(target=_proc_writer, args=(str(p), pid, nkey))
             for pid in range(nproc)]
    for pr in procs:
        pr.start()
    for pr in procs:
        pr.join(timeout=60)
        assert pr.exitcode == 0
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    # every (process, key) pair must survive
    for pid in range(nproc):
        for i in range(nkey):
            assert on_disk[f"f{pid}_{i}::d{pid}"]["lr_positive"] == pid * 100 + i
    assert len(on_disk) == nproc * nkey


def test_namespace_isolation_paths():
    """Concern #3 (experiment): namespaced caches are distinct files per arm."""
    # The controller derives `<base>.ns_<arm>.json`; verify the naming is
    # collision-free across arms (string-level contract used by controller).
    base = "rag_lr_secondary_cache.json"
    a = base[:-5] + ".ns_armA.json"
    b = base[:-5] + ".ns_armB.json"
    assert a != b and a.endswith(".json") and "armA" in a
    # a namespaced file is NOT auto read-only (it is a per-arm WRITABLE cache)
    import tempfile, os as _os
    d = tempfile.mkdtemp()
    p = _os.path.join(d, a)
    open(p, "w").write("{}")
    assert SecondaryLRCache(p).read_only is False
