# セッション引き継ぎブリーフ (2026-06-04)

旧セッション（`f265f231-…` / そのコピー `d62e6af6-…`）は**ファイル破損ではなく容量超過**で
継続不能（`internal error`）。約 391 万文字・100 万トークン超・ツール呼び出し 2,601 回まで
肥大化し、Cursor が継続時に全履歴を 1 リクエストに詰めて送る段階で上限を超えるのが原因。
転写 `.jsonl` を編集してもアプリ内継続は直らないため、**新しい会話を開き、本ファイルと
関連設計文書を文脈として渡して続行する**こと。作業成果はすべてリポジトリに保存済み。

## プロジェクト目標
「面向视频问答的组合式推理 v3」のツリー推理アルゴリズムを臨床診断領域へ適用する
（Tree-Dx-Spec パイプライン：RootSelector → BranchCreator → SubBranchCreator → TALP →
Bundler → EvidenceAnnotator）。

## 主要な現状（done）
- 知識統合の二大通道は設計・一部実装済み：
  - 通道 A：多層 LR 検索 → `EvidenceAnnotator`（`lr_reference`）。
  - 通道 B：`DxFeatureRetriever` → `TALP`（`discriminator_hints`、ただし
    `enable_knowledge_injection` は既定 OFF）。
- §16.9 安全性審査（LR 衰減公式・反向排除信号）完了。
- §16.9.7：実 USMLE データセット（medbullets）で発見した**超短抗体略語の同形異義
  バグ**（sma/ama/ema/hbs）を上下文消歧で修復（誤排除 25→0、7/7 テスト合格）。
- §16.9.8：手書きブラックリストを**エンティティリンキング/概念正規化**で自動化する
  方針を調査。T0 自動歧義検出器を実装
  （`scripts/build_auto_ambiguity_map.py` → `data/knowledge_raw/auto_ambiguity_map.json`、
  自動抽出 6 語：acpa/ama/asma/ema/hbs/sma）。派生 cue の自指バグも修正済み。
  注意：`finding_synonym_bridge.json` の `cui` は 398,218 件中**有効 112 件のみ**で
  当初の「全件 CUI 付き」前提は実測で不成立 → 決定論的なオフライン代替で実装。

## いま着手中／次の一手（最重要）
**§19「各编排环节知识注入方案」(v1.7) は設計調研まで完了、実装は未着手。**
controller が能動的に知識層を引いて payload を埋める方式へ（LLM 自報の stub 依存をやめる）。
優先度：

1. **【高】BranchCreator 知識通道の新設**（最大の欠口）
   - `create_branches`（`controller.py`）呼び出し前に能動注入。
   - 新規 payload 字段：`candidate_disease_families` / `subtype_links`(PrimeKG `disease_disease`
     亜型エッジ、phase-crossing 用) / `axis_hints`。
   - 復用：`PrimeKGIndex.get_related_diseases` / `search_diseases` + `DiseaseNameResolver` /
     `DxFeatureRetriever.get_discriminator_hints`。
   - 新規 config 開関 `enable_branch_knowledge`（既定 OFF）、stub 兜底を保持。
2. 【中】RootSelector：`candidate_syndromes` / `alarm_phenotype_hits` 注入
   （`enable_root_knowledge` 既定 OFF）。
3. 【中】SubBranchCreator：BranchCreator 通道を分支 label 起点で復用
   （`parent_subtypes` / `sibling_discriminators`）。
4. 【中】TALP 補強：`lr_reference` 追加 + pathognomonic markers（`DiagnosticMarkerIndex`
   + `MarkerDisambiguator`）注入、A/B 後に既定 ON 化を判断。

共通原則：controller 主動注入 / 独立開関 + 安全回退（fail-open）/ 字段化 + prompt 明示参照
+ top-k で token 抑制。

## 参照すべきファイル
- `EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md` … 設計の正本（§16.9〜§19 が最新）。
- `agentclinic_tree_dx_spec.md` / `IMPLEMENTATION_STATUS.md` … 実装仕様・進捗。
- `src/agentclinic_tree_dx/knowledge/diagnostic_marker_index.py` … marker + 消歧ロジック。
- `scripts/build_auto_ambiguity_map.py`, `scripts/mine_medbullets_cases.py` … 関連スクリプト。
- `CONVERSATION_EXPORT.md` … 旧会話の全文エクスポート（必要時のみ部分参照）。

## 新セッションの始め方（推奨）
本ファイル + `EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md`（特に §19）を添付し、
「§19.4 の BranchCreator 知識通道を実装したい」から再開するのが最短。
