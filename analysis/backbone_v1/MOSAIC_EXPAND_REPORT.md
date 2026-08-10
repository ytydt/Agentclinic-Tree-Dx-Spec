# MOSAIC 扩集报告（统一 DA400 / MCR400 口径）

依据：`PROMISING_POST_AUDIT_ALGORITHM_CANDIDATES.md`  
实现：`src/agentclinic_tree_dx/mosaic.py`  
模型：`meta-llama/llama-3.3-70b-instruct`  
日期：2026-08-08  

机器可读全表：`analysis/backbone_v1/mosaic_eval/leaderboard_400.json`

---

## 0. 报告口径（唯一）

| 规则 | 内容 |
|------|------|
| 评价单元 | **DA400** 与 **MCR400** 分开报告；**不做** seq100 / heldout / 200b / pooled200 等局部口径 |
| 入表条件 | 双数据集合计 **800 题均有完整 task 标签** |
| Task | DA = `option@1`；MCR = official `diagnostic_hit`；R4 基线 = `*_scored_correct` |
| Concept | 运行臂 = `dc.match(champion, gold)`；R4 基线 = `*_chain_correct` |
| 检验 | McNemar（双侧 exact），记 **A–B wins** 与 p；一律 n=400 |

**入表方法（800 齐全）：** Lite、Forest、IMPC、B07、MAC(B06)、e7、v0、I1(e7-S4a)。  

**不入主表（未满 800）：** Adaptive-4 / Adaptive-4v2、B01、APHHM、I2/I3/I5、I4（有预测无完整评分）。

---

## 1. 主表（DA400 / MCR400）

| 方法 | 约 calls | DA400 task | DA400 concept | MCR400 task | MCR400 concept |
|------|--------:|-----------:|--------------:|------------:|---------------:|
| **Forest** | 4.03 | **0.6375** | 0.2800 | 0.2650 | 0.2525 |
| IMPC | 4.00 | 0.6250 | 0.2925 | 0.2425 | 0.2375 |
| B07 | 3 | 0.6150 | 0.2625 | 0.2650 | 0.2825 |
| MAC (B06) | ≫4† | 0.6150 | **0.3300** | **0.2750** | **0.3150** |
| Lite | 3.00 | 0.6025 | 0.2575 | 0.2550 | 0.2175 |
| e7 | 6 | 0.5700 | 0.2025 | 0.2625 | 0.2025 |
| v0 | 4 | 0.5525 | 0.1750 | 0.2500 | 0.2125 |
| I1 (e7-S4a) | 3 | 0.5450 | 0.2025 | 0.2250 | 0.2025 |

† MAC 为多轮讨论式多代理，预算高于 Forest；表中为性能对照，非严格等预算。  
Task 列按 DA400 降序；并列时看 MCR task / concept。

---

## 2. 配对检验（相对 Forest，n=400）

| 方法 | DA task | DA concept | MCR task | MCR concept |
|------|---------|------------|----------|-------------|
| Lite | 31–45，p=0.135 | 19–28，p=0.243 | 15–19，p=0.608 | **8–22，p=0.016**（Lite 更差） |
| IMPC | 34–39，p=0.640 | 20–15，p=0.500 | 13–22，p=0.176 | 15–21，p=0.405 |
| B07 | 41–50，p=0.402 | 30–37，p=0.464 | 22–22，p=1.000 | 33–21，p=0.134 |
| MAC | 38–47，p=0.386 | **36–16，p=0.008**（MAC 更好） | 24–20，p=0.652 | **34–9，p=0.0002**（MAC 更好） |
| e7 | **46–73，p=0.017**（Forest 更好） | **20–51，p=0.0003** | 25–26，p=1.000 | **14–34，p=0.006** |
| v0 | **44–78，p=0.003** | **19–61，p&lt;0.001** | 24–30，p=0.497 | **20–36，p=0.044** |
| I1 | **43–80，p=0.001** | **17–48，p=0.0002** | **15–31，p=0.026** | **14–34，p=0.006** |

记法：第一数字 = 该方法独赢，第二 = Forest 独赢。

### 其他关键对照（同口径，A–B wins）

| 对比 | DA task | DA concept | MCR task | MCR concept |
|------|---------|------------|----------|-------------|
| Lite vs B07 | 52–57，p=0.702 | 32–34，p=0.902 | 28–32，p=0.699 | **18–44，p=0.001**（Lite 更差） |
| Lite vs MAC | 43–48，p=0.675 | **16–45，p=0.0003** | 19–27，p=0.302 | **8–47，p&lt;0.001** |
| Lite vs e7 | 60–47，p=0.246 | **45–23，p=0.010** | 28–31，p=0.795 | 30–24，p=0.497 |
| IMPC vs Lite | 43–34，p=0.362 | 32–18，p=0.065 | 19–24，p=0.542 | 26–18，p=0.291 |
| IMPC vs B07 | 51–47，p=0.762 | 44–32，p=0.207 | 22–31，p=0.272 | **22–40，p=0.030**（IMPC 更差） |
| IMPC vs MAC | 48–44，p=0.755 | **18–33，p=0.049** | 15–28，p=0.066 | **11–42，p&lt;0.001** |
| Forest vs B07 | 50–41，p=0.402 | 37–30，p=0.464 | 22–22，p=1.000 | 21–33，p=0.134 |
| Forest vs MAC | 47–38，p=0.386 | **16–36，p=0.008** | 20–24，p=0.652 | **9–34，p=0.0002** |

其余两两配对见 `leaderboard_400.json` → `mcnemar_all_pairs`。

---

## 3. 机制指标（仅 MOSAIC，DA400）

| 方法 | mean calls | G 间 Jaccard | exact dup max | history leak |
|------|-----------:|-------------:|--------------:|-------------:|
| Lite | 3.00 | 0.309 | 0 | 0 |
| Forest | 4.03 | 0.416 | 0 | 0 |
| IMPC | 4.00 | 0.481 | 0 | 0 |

均远低于历史 MAC echo（Jaccard≈0.97）。

---

## 4. 结论（仅基于上表）

1. **Task**：Forest 在 DA400 点估计最高（0.638），显著优于 e7 / v0 / I1；相对 B07、MAC、Lite、IMPC **均不显著**。MCR400 task 与 B07 打平（0.265），略低于 MAC（0.275），均不显著。  
2. **Concept**：Forest 显著优于 e7 / v0 / I1 / Lite（MCR）；**显著低于 MAC**（DA 与 MCR）。相对 B07 不显著。  
3. **Lite**：3-call 骨干；task 接近 B07，concept 弱于 Forest（MCR 显著）与 MAC。  
4. **IMPC**：隔离基线；DA concept 点估计略高于 Forest，task（尤其 MCR）不强。  
5. **不可宣称**：Forest 击败 MAC；可写「DA task 点估计领先且显著优于 e7 系；concept 仍落后 MAC；MCR task ≈ B07」。

---

## 5. Go / No-Go

| 方法 | 判决 |
|------|------|
| Lite | 保留为 3-call 默认臂 |
| Forest | 保留为 ~4-call 主扩展臂（对 e7 系有显著优势；对 MAC concept 仍落后） |
| IMPC | 机制基线，非主结果臂 |
| Adaptive-* | 未满 800，且先前局部实验伤 concept → 不扩、不入主表 |
| I1 | 已满 800，但全面弱于 Forest / 骨干基线 → 不作推荐臂 |

---

## 6. 产物路径

| 路径 | 内容 |
|------|------|
| `logs/backbone_v1/*/mosaic_{lite,forest,impc}_v1` | 三臂全 800 预测与评分 |
| `analysis/backbone_v1/r4_facts/pooled.tsv` | e7/v0/MAC/B07 的 800 双指标 |
| `analysis/backbone_v1/mosaic_eval/leaderboard_400.json` | 本报告数值与全部配对检验 |
| `analysis/backbone_v1/r4_run_mosaic_expand.sh` / `r4_run_mosaic_400b.sh` | 扩集启动脚本 |
