"""§26.5(1) regression: secondary-cache LR detox (neutralize_entry).

Drops demographic/normal-exam findings; softens ONLY manufactured exclusion
(default-specificity single-sided LRs); leaves support, explicit, and
non-default-specificity entries untouched.
"""

from agentclinic_tree_dx.knowledge.lr_quant import (
    neutralize_entry,
    is_nondiscriminative_finding,
)


def test_demographic_findings_detected():
    assert is_nondiscriminative_finding("Patient is a 57-year-old man")
    assert is_nondiscriminative_finding("Age and gender: 59-year-old man")
    assert is_nondiscriminative_finding("Physical exam: within normal limits")
    assert is_nondiscriminative_finding("Physical appearance: athletic young woman")
    assert not is_nondiscriminative_finding("35% blasts in peripheral blood")
    assert not is_nondiscriminative_finding("splenomegaly")


def test_demographic_entry_dropped():
    e = {"finding": "Hypertension", "disease": "x", "specificity": 0.85,
         "lr_positive": 0.0667, "lr_negative": 1.1647, "provenance": "pct:1%",
         "confidence": "rag_extracted"}
    # "Hypertension" is non-specific but not demographic by our detector; it is
    # softened (not dropped). Use a demographic finding for the drop case:
    d = {"finding": "Patient is a 57-year-old man", "disease": "x",
         "specificity": 0.85, "lr_positive": 0.0667, "lr_negative": 1.1647,
         "provenance": "pct:1%", "confidence": "rag_extracted"}
    assert neutralize_entry(d) is None
    assert neutralize_entry(e) is not None  # softened, not dropped


def test_manufactured_exclusion_softened():
    e = {"finding": "Hypertension", "disease": "cml", "specificity": 0.85,
         "lr_positive": 0.0667, "lr_negative": 1.1647, "provenance": "pct:1%",
         "confidence": "rag_extracted"}
    out = neutralize_entry(e)
    assert out["lr_positive"] == 0.5      # clamped up toward neutral
    assert out["lr_negative"] == 1.1647   # mild LR- (≤2) left as-is
    assert out["confidence"] == "rag_qualitative"
    assert "detox_clamped" in out["provenance"]


def test_support_direction_untouched():
    e = {"finding": "splenomegaly", "disease": "cml", "specificity": 0.85,
         "lr_positive": 4.67, "lr_negative": 0.3, "provenance": "phrase:frequent",
         "confidence": "rag_qualitative"}
    out = neutralize_entry(e)
    assert out["lr_positive"] == 4.67     # support not clamped
    assert out["lr_negative"] == 0.3


def test_explicit_and_nondefault_sp_untouched():
    explicit = {"finding": "blasts", "disease": "cml", "specificity": 0.85,
                "lr_positive": 0.05, "lr_negative": 1.1,
                "provenance": "explicit:Sn+Sp", "confidence": "rag_extracted"}
    assert neutralize_entry(explicit)["lr_positive"] == 0.05  # real Sp → trust

    nondefault = {"finding": "leukocytosis", "disease": "cml", "specificity": 0.70,
                  "lr_positive": 0.1, "lr_negative": 1.2,
                  "provenance": "phrase:frequent", "confidence": "rag_qualitative"}
    assert neutralize_entry(nondefault)["lr_positive"] == 0.1  # non-default Sp
