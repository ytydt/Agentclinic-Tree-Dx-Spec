# OX Recall 偏低根因审计（人工+批量）

状态：审计结论  
日期：2026-07-26  
协议：全局叶后验 Top-5 × lexical `greedy_set_match`（thr=0.7）  
基线：R=**0.473**（222/469 金标条）；与 `official_eval` lexical 一致  
证据：`ox_recall_miss_taxonomy.json`（247 条未命中金标）

---

## 0. 总判（回答你的选项）

| 假设 | 是否主因 | 占未命中 | 占全部金标 | 说明 |
|------|----------|----------|------------|------|
| **L2 排序把金标挤出 Top-5** | **是，第一主因** | **41.7%** | **22.0%** | 叶在树上且 `leaf_match≈1.0`，但 dedup 后验秩 ≥6 |
| **L2 真缺失（叶未生成）** | **是，第二主因** | **~42%**（含假朋友/轴错） | **~22%** | 树上无对应叶；多数时 L1/轴尚在，属补叶失败 |
| **粒度不一致（金标伞名 vs 系统亚型）** | 次主因 | **~13%** | **~7%** | 如 CAP↔各病原肺炎；IEM 伞名↔氨基酸病叶 |
| **同义词/NER 未识别** | **否，非主因** | **&lt;3%** | **&lt;1.5%** | D 类几乎都是精确名命中；纯同义漏检很少 |
| **L1 真缺失（轴/MECE 全错）** | 部分叠加在 C | 子集 | — | C 中约 72/74 与任一轴无词重叠→常是轴选错或叶未挂到轴下 |
| **一对一贪心碰撞 / 近义混淆** | 次要 | **2.8%** | **1.5%** | 如 gout 占坑致 pseudogout 未计；间质性肾炎↔DI-AKI |

**一句话**：Recall 低 ≈ **一半是排序截断（叶在但进不了 Top-5）+ 一半是覆盖洞（叶不在 / 伞名对不上亚型）**；不是「同义词匹配器坏了」。

---

## 1. 未命中结构（247 = 469−222）

```
D  排序截断 ████████████████████ 103 (41.7%)
C  叶缺失   ███████████████░░░░░ ~105 (42.5% 含假朋友/错误轴)
B  粒度     █████░░░░░░░░░░░░░░░  32 (13.0%)
A/Z 匹配器  █░░░░░░░░░░░░░░░░░░░   7 ( 2.8%)
```

### What-if（只改一类能抬多少 R）

| 干预 | 可达 R（lexical） | ΔR |
|------|------------------:|---:|
| 现状 Top-5 | 0.473 | — |
| 收尽 D（叶内完美排序 / 更大 K） | **0.693** | +0.220 |
| 收尽 A/B/Z（粒度+匹配） | 0.557 | +0.083 |
| D+A/B/Z 都收尽 | **~0.78** | +0.30 |
| 剩余真缺失 C | 约占金标 **22%** | 需生成/补叶 |

对照：全 L2 叶 R≈0.70 ≈「收尽 D」的上界——与先前 divergence 审计一致。

---

## 2. 各类证据（含手检病例）

### 2.1 D — L2 排序截断（主因 #1）

定义：存在叶使 `leaf_match_score(gold, leaf)≥0.7`，但 label-dedup 后验秩 **&gt;5**。

| 统计 | 值 |
|------|-----|
| 条数 | 103 |
| 秩分布 | 6:24, 7:19, 8:12, 9:12, 10:8, …（中位 **8**，P90 **13**） |
| Top-7 可救回 | 43/103 = **42%** |
| Top-10 可救回 | 75/103 = **73%** |

手检：

| case | 金标 | 树上叶 | 后验秩 | Top-5 |
|------|------|--------|--------|-------|
| 1 | diabetic nephropathy | Diabetic Nephropathy @1.0 | **13** | DI-AKI, CIN, … |
| 3 | ankylosing spondylitis | Ankylosing Spondylitis @1.0 | **6** | OA/RA/PsA/Gout/… |
| 4 | Hirschsprung disease | Hirschsprung Disease @1.0 | **6** | 旋转不良/十二指肠闭锁/… |
| 20 | choledochal cyst | Choledochal Cyst @1.0 | **10** | 新生儿肝炎/胆道闭锁/… |

→ **不是命名问题**，是 joint/后验没有把已有金标叶排进提交窗。

### 2.2 C — L2 真缺失 / 覆盖洞（主因 #2）

树上无 ≥0.7 叶匹配；轴/L1 也常对不上具体病名。

手检「真不在叶集」：

| case | 金标 | Top-5 / 树主题 | 审计读法 |
|------|------|----------------|----------|
| 2 | tuberculosis | 组织胞浆菌/芽生菌/球孢子菌… | L1 有 Bacterial Infection，但 **未生成 TB 叶** |
| 4 | meconium ileus / plug | 旋转不良/闭锁… | 轴有梗阻/先天，**特异性叶缺失** |
| 7 | neuroleptic malignant syndrome | 迟发障碍/肌张力障碍… | 药源性运动轴下 **无 NMS** |
| 8 | DIC / PNH | HUS/TTP/AIHA | 溶血轴下 **无 DIC/PNH** |
| 12 | PID | IBD/IBS/子宫内膜异位 | **轴跑偏到胃肠**；PID 叶不存在 |

C 中 **72/74** 与任一非叶轴无共享内容词 → 多为 **MECE/生成未覆盖**，不是「有叶但同义词没对上」。

### 2.3 B — 粒度不一致（次主因）

金标偏伞名/上位，系统只有下位叶；`leaf_match_score` 不给分。

| case | 金标（伞） | 树上已有（亚型） | 应否算「系统知道」 |
|------|------------|------------------|-------------------|
| 2 | community-acquired pneumonia | Pneumococcal / Hib / Mycoplasma / Other Bacterial Pneumonias | 临床相关，**匹配过严/粒度** |
| 4 | intestinal atresia | Duodenal / Jejunoileal Atresia | 同上 |
| 14 | neonatal sepsis | Bacterial Sepsis | 同上 |
| 20 | inborn errors of metabolism | Amino/Organic/Fatty-acid/Carbohydrate Disorders + 轴 IEM | **轴在叶细分**；伞名金标打不中 |
| 23 | allergic reaction | 轴 Allergic Reaction | 轴级命中、无叶 |

→ 若评测允「父↔子」，R 可再抬一截；属 **协议/粒度**，非树完全没病。

### 2.4 A — 同义词 / NER？

**反证**：D 类 103 条几乎都是大小写级精确命中（score=1.0）。  
真正像「同义没对上」的很少；更常见是：

- **近义混淆 + 一对一**：`pseudogout` 对 Top-5 里 `Gout` 打出 0.92，但 `Gout` 已配给金标 gout，贪心不再给 pseudogout；同时 Pseudogout 叶本身可能未进 Top-5。
- **亚型表述**：`drug-induced interstitial nephritis` ↔ `Drug-Induced Acute Kidney Injury`（0.76，临床近但不等于同义）。

**结论**：主表 R 低 **不能**归因于「医学同义词表失效」。

### 2.5 L1 真缺失？

不全是「L1 全灭」，而是分层：

| 模式 | 例子 | 含义 |
|------|------|------|
| L1/轴合理但叶未展开 | TB（有 Bacterial）、胎粪性肠梗阻（有梗阻轴） | **L2 生成洞** |
| L1/轴与金标错位 | case12 盆腔炎 vs IBD 轴；case14 胆道闭锁落在溶血主题树 | **L1/MECE 选轴错误** |
| 金标伞名停在轴 | IEM / allergic reaction | **粒度（轴在叶不在或未对齐）** |

故：**L1 真缺失是 C 的一部分机制，不是独立第一名**；与 L2 缺失常同案出现。

---

## 3. 根因优先级（工程含义）

1. **抬 R 最快（不改树）**：加大提交 K（7–10）或改进后验/joint，把已在叶集的金标排进窗口 → 理论 +0.22 R（lexical）。  
2. **第二刀（要改生成）**：对 C 类做 L2 补叶 / 召回（TB、胎粪栓、NMS、DIC…）→ 消化约金标 15–22%。  
3. **评测协议**：对伞名金标允许父⊇子匹配，可吃掉 B（~7% 金标），但需单列协议，避免灌叶虚高 P。  
4. **匹配器**：同义词不是瓶颈；可修 gout/pseudogout 类近义一对一，收益小（~1.5%）。

---

## 4. 与「全 L2 R≈0.70」的闭合

全叶 R 高，是因为 D 类在全叶集合里被算进 TP。  
Top-5 R 低，主要是把这些 TP **截掉**，再加上 C/B 本来全叶也救不回（或不按伞名计）。  
这与 [`ox_eval_metric_divergence_audit.md`](ox_eval_metric_divergence_audit.md) 的截断账（ΔTP≈108）一致。

---

## 5. 产物

| 文件 | 内容 |
|------|------|
| [`ox_recall_miss_taxonomy.json`](ox_recall_miss_taxonomy.json) | 逐条金标未命中 + `refined_bucket` |
| 本文 | 人工核验后的根因裁定 |

**审计裁定**：Recall 偏低的主因是 **(1) L2 排序截断** 与 **(2) L2/轴覆盖缺失（含部分 L1 错轴）**；粒度不一致为第三；**同义词识别失败不是主因**。

### 续：C 类缺叶再拆（KB vs LLM）

见 [`ox_c_leaf_absent_rootcause.md`](ox_c_leaf_absent_rootcause.md)。  
结论：**主因不是 KB 缺失**，而是 Config A 热路径上 **LLM 入口已提名 / Creator 偶发写出但未稳定落进最终短窗**（C2≈2/3）；并发现 taxonomy 叶宇宙误用 `shared_trees`（≠ Config A 终态树）导致部分假 C。
