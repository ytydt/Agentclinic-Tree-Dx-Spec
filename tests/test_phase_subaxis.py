"""§26.5(4)/§27.2 regression: phase / opposite-direction sub-axis split.

§27.2 fix changed split semantics from REPLACE to ADDITIVE: when split=True the
broad parent domain is KEPT and the opposite-direction variant (blast crisis) is
ADDED alongside it — so the gold entity (e.g. CML) always retains its broad home
branch while the can't-miss acute subset gets its own node.
"""

from pathlib import Path

from agentclinic_tree_dx.knowledge.syndrome_axis import SyndromeAxisMap

MAP = Path(__file__).resolve().parents[1] / "data" / "knowledge_raw" / "syndrome_axis_map.json"


def _entry():
    m = SyndromeAxisMap.from_file(MAP)
    e = m.match("marked leukocytosis with 35% blasts")
    assert e.get("id") == "leukocytosis"
    return m, e


def test_legacy_domain_lumped_when_split_off():
    m, e = _entry()
    names = m.domain_names(e, split=False)
    assert any("incl. MPN / blast-bearing" in n for n in names)
    assert not any("increased blasts / blast crisis" in n for n in names)


def test_domain_additive_when_on():
    m, e = _entry()
    names = m.domain_names(e, split=True)
    # §27.2 ADDITIVE: broad parent is KEPT and the blast-crisis variant ADDED.
    assert any(n == "myeloid neoplasm (incl. MPN / blast-bearing)" for n in names)
    assert any("increased blasts / blast crisis" in n for n in names)


def test_projection_keeps_cml_in_parent_routes_blast_to_variant():
    m, e = _entry()
    # §27.2: plain CML stays in the broad parent (its gold home); an explicit
    # blast-crisis / acute entity routes to the added variant.
    chronic = m.project_entity("chronic myeloid leukemia", e, split=True)
    blast = m.project_entity("chronic myeloid leukemia in blast crisis", e, split=True)
    aml = m.project_entity("acute myeloid leukemia", e, split=True)
    assert chronic == "myeloid neoplasm (incl. MPN / blast-bearing)"
    assert blast and "blast crisis" in blast
    assert aml and "blast crisis" in aml
    assert chronic != blast
