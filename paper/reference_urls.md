# Reference URL list (delivery artifact)

32 bibliography keys in `paper/references.bib`. Primary landing URLs below.

## Datasets / benchmarks
1. DiagnosisArena — https://aclanthology.org/2026.findings-acl.151/ (arXiv: https://arxiv.org/abs/2505.14107 ; code: https://github.com/SPIRAL-MED/DiagnosisArena ; HF: https://huggingface.co/datasets/shzyk/DiagnosisArena)
2. MedCaseReasoning — https://arxiv.org/abs/2505.11733 (code: https://github.com/kevinwu23/Stanford-MedCaseReasoning ; HF: https://huggingface.co/datasets/zou-lab/MedCaseReasoning)
3. Dual-Inf / Open-XDDx — https://www.nature.com/articles/s44401-025-00015-6 (code/data: https://github.com/betterzhou/Dual-Inf)
4. SDBench / MAI-DxO — https://arxiv.org/abs/2506.22405
5. H-DDx — https://arxiv.org/abs/2510.03700
6. RareBench — https://dl.acm.org/doi/10.1145/3637528.3672114 (code: https://github.com/chenxz1111/RareBench)
7. MedQA — https://www.mdpi.com/2076-3417/11/14/6421
8. DDXPlus — https://arxiv.org/abs/2205.09148 (code: https://github.com/mila-iqia/ddxplus)

## External baselines / related systems
9. MEDDxAgent — https://aclanthology.org/2025.acl-long.677/ (code: https://github.com/nec-research/meddxagent)
10. MDAgents — https://arxiv.org/abs/2404.15155 (code: https://github.com/mitmedialab/MDAgents)
11. MAC (original) — https://www.nature.com/articles/s41746-025-01550-0
12. Mixed-vendor MAC — https://aclanthology.org/2026.healing-1.1/ (arXiv: https://arxiv.org/abs/2603.04421 ; code: https://github.com/rajpurkarlab/mixed-vendor-mac)
13. KG4Diagnosis — https://arxiv.org/abs/2412.16833
14. DeepRare — https://www.nature.com/articles/s41586-025-10097-9 (arXiv: https://arxiv.org/abs/2506.20430)
15. Chain-of-Diagnosis / DiagnosisGPT — https://aclanthology.org/2025.findings-acl.740/ (code: https://github.com/FreedomIntelligence/Chain-of-Diagnosis)
16. MedRAG (KG-elicited, WWW'25) — https://dl.acm.org/doi/10.1145/3696410.3714782 (code: https://github.com/SNOWTEAM2023/MedRAG)
17. MedRAG toolkit / MIRAGE — https://aclanthology.org/2024.findings-acl.372/ (code: https://github.com/Teddy-XiongGZ/MedRAG)
18. i-MedRAG — https://arxiv.org/abs/2408.00727
19. Medprompt — https://arxiv.org/abs/2311.16452

## Foundational methods
20. Chain-of-Thought — https://arxiv.org/abs/2201.11903
21. Self-Consistency — https://arxiv.org/abs/2203.11171
22. Self-Refine — https://arxiv.org/abs/2303.17651
23. RAG (Lewis et al.) — https://arxiv.org/abs/2005.11401
24. Reciprocal Rank Fusion — https://dl.acm.org/doi/10.1145/1571941.1572114
25. Llama 3 herd (incl. 3.3-70B-Instruct) — https://arxiv.org/abs/2407.21783

## Statistics
26. Holm (1979) — https://www.jstor.org/stable/4615733
27. McNemar (1947) — https://doi.org/10.1007/BF02295996

## Notes
- BibTeX keys: `diagnosisarena`, `medcasereasoning`, `dualinf2025`, `sdbench2025`, `hddx2025`, `meddxagent2025`, `mdagents`, `chen2025mac`, `mac2026`, `kg4diagnosis`, `deeprare2025`, `chainofdiagnosis`, `medrag`, `xiong2024medrag`, `imedrag`, `medprompt`, `wei2022cot`, `wang2023selfconsistency`, `madaan2023selfrefine`, `lewis2020rag`, `rrf2009`, `llama33`, `holm1979`, `mcnemar1947`, `rarebench`, `jin2021medqa`, `fansi2022ddxplus`.
- Compile with: `pdflatex main && bibtex main && pdflatex main && pdflatex main` from `paper/`.
