# i-MedRAG pin

Upstream: [Teddy-XiongGZ/MedRAG](https://github.com/Teddy-XiongGZ/MedRAG)
(i-MedRAG = `rag=True, follow_up=True`; arXiv:2408.00727 / PSB 2025).

Pinned commit recorded in `adapter.py` (`UPSTREAM_COMMIT`).

```bash
git clone https://github.com/Teddy-XiongGZ/MedRAG.git baselines/imedrag/upstream
```

## Runtime policy

| Piece | Source |
|-------|--------|
| Iterative follow-up loop + prompt roles | Official `src/medrag.py` / `template.py` |
| LLM | Project `RobustLLMClient` / shared backbone |
| Knowledge | **Only** `data/corpus/rag_index` + `data/corpus/cpg_index` |

Do **not** download MedRAG Textbooks / PubMed / Wikipedia corpora for this arm.

Arm id: `B17-imedrag`.
