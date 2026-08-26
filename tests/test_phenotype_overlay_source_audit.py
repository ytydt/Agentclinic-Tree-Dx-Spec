from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from analysis.mechanism_v2.phenotype_overlay_source_audit import (
    audit_medlineplus,
    run,
)


ROOT = Path(__file__).resolve().parents[1]
CARDS = ROOT / "data/knowledge_raw/phenotype_prototype_cards_v2.json"


class PhenotypeOverlaySourceAuditTest(unittest.TestCase):
    def test_medlineplus_excludes_third_party_site_text(self) -> None:
        xml = """<?xml version='1.0'?>
<health-topics date-generated='test'>
  <health-topic title='Example' url='https://example.test' id='1' language='English'>
    <full-summary><![CDATA[<p>Symptoms include fever and edema.</p>]]></full-summary>
    <site title='External'><information-category>Other</information-category>
      <organization>Third party</organization>
      <standard-description>Symptoms include secret commercial text.</standard-description>
    </site>
  </health-topic>
</health-topics>"""
        targets = [
            {
                "prototype_id": "P",
                "target_id": "LOCAL:P",
                "label": "secret commercial text",
                "aliases": ["secret commercial text"],
                "ontology_anchors": [],
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "fixture.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("fixture.xml", xml)
            summary, rows = audit_medlineplus(archive, targets)
        self.assertEqual(summary["target_mentions"]["P"]["n_topics"], 0)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("secret commercial", json.dumps(rows))

    def test_frozen_build_has_no_combinations_or_dynamic_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            summary = run(
                ROOT
                / "data/knowledge_raw/phenotype_overlay_sources/medlineplus/"
                "mplus_topics_compressed_2026-08-25.zip",
                ROOT
                / "data/knowledge_raw/phenotype_overlay_sources/orphadata/"
                "en_product4_2026-07.xml.gz",
                ROOT
                / "data/knowledge_raw/phenotype_overlay_sources/hoom/"
                "hoom_orphanet_2.6.zip",
                CARDS,
                ROOT
                / "data/knowledge_raw/phenotype_overlay_sources/dismech/"
                "93a6b51f5821868fd364b51010424e41045f2b5e/kb/modules",
                output,
            )
            manifest = json.loads((output / "source_manifest.json").read_text())
        self.assertEqual(
            summary["complexity_contract"]["pair_or_triple_rows_materialized"], 0
        )
        self.assertEqual(summary["orphadata"]["n_disorders"], 4357)
        self.assertEqual(summary["hoom"]["version"], "2.6")
        self.assertEqual(summary["hoom"]["n_associations"], 116858)
        self.assertEqual(
            summary["hoom"]["diagnostic_criterion_attribute_counts"],
            {"Criterion_DC": 1096, "Exclusion_DC": 733, "Pathognomomic_DC": 19},
        )
        self.assertEqual(
            sum(summary["hoom"]["target_diagnostic_criterion_counts"].values()), 4
        )
        self.assertNotIn("created_at", manifest)
        self.assertEqual(manifest["ledger_date"], "2026-08-25")
        relation_counts = {}
        for row in summary["targets"]:
            relation = row["ontology_anchor_relation"]
            relation_counts[relation] = relation_counts.get(relation, 0) + 1
        self.assertEqual(relation_counts, {"identity": 3, "related_query_only": 3})
        self.assertEqual(manifest["builder"]["python_dependency"], "PyYAML>=6.0")
        self.assertEqual(
            manifest["sources"]["orphadata"]["xml_content_sha256"],
            "4f44e8a61201399911aa1ba44a293c0ccaa5ce11272c47d40862255cb72f6b32",
        )
        self.assertEqual(manifest["network_calls_during_build"], 0)
        self.assertEqual(manifest["new_llm_calls"], 0)


if __name__ == "__main__":
    unittest.main()
