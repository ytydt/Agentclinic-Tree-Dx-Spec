"""Frozen root decisions for the exhaustive E2 consensus-correction sweep.

Each character maps positionally to ``root_audit/consensus_sweep_cards.jsonl``
(S0001 through S1070).  The root auditor reviewed the candidate-reference
relation with clinical context but without the separate index containing case
keys, method family, arm outputs, strict/task outcomes, mapper status, sampling
strata, reviewer-pair labels, or the sweep trigger.

The two original heterogeneous reviewers and the post-freeze GPT reviewer were
treated as fallible subcontractor evidence.  They did not vote the endpoint:
the root review corrected 70 original consensus-partial records to a
non-accepted relation and restored three original non-accepted records as
partial.  Fine categories retain the frozen E2 relation ontology.
"""

CONSENSUS_SWEEP_RELATION_CODES = (
    "NNPMXPPPPPPMMXPNPXPPXPPXPPPPPNPXXNPXPNPNNNMPMPPPPMXMMMMMMPPPNNXPPNNNNNPNNNMMMNMM"
    "MMNPPPPMXPPPNNNMPMPPMNPPNNNNPMPNXPXXMMNNPNPNPMMPPNNNNNNPNMPPPMPPNNNNNMPXPPMMXPPP"
    "NPPMMPMNMNPPMNXPXNXNNNNNNPNPXNXPXNNNNNMNNMMPMPPMPNPPPNNNNNPPPPPNPPPNPPMMPPPXPPPP"
    "PPPMPPPPNPXPPNNPMPMPPPPXMPPMPPMPPPPPPPNNPPPPPPNPPMNNPPNPPPPPPPPPPPNPNNPNNNNNNPPN"
    "PMNNMXMMMPPPPPMMMMNMPPPPXXXXPPPPPPPPPPPPPPPPPNPPPNPMPPXPPXPPPXPPPXPPPXPPXPPPPPNN"
    "NNXNNNNNNPMMPMXNMPNPPMPMPPPPPPNPXNPPPPNNMMNXPNNPPPPNNNNXMMNNNPPPMPNMXNXNPPPNPMPP"
    "PPPPPPPPPNNNNNNNNPXNNPPPPXNXNNNPPNPPPPNPNMNNPPPPPPPPPNPPPPPPPXXXPPXXPPPXMNPPMPPM"
    "NPMNXNPXPPPNPXPPPXPXXNMPMPPMPPNPXPXNPPPNPPMPPMPNNPPNNPNNMPNPNPPPPXXPPPXPPPPPMNMM"
    "MMMMPPNXNPMNNNNPPNNNPXXXXNMMMNMMNNPNNNMPMMMMMNNPPNNNNNPPPNPNPPPXXPXPNXPMXXPPPXMX"
    "MMXMMMXPNXNNNNNNNNNNXPMMNPNMNXPPXMMNNNPNNPMPMPPMXNNMMMMPPXXPMNNNNNMMNNPPNMNNNPPN"
    "MNMNMNPMMNPMPMMMNMNPPNPPPNMPMMMMXNXPNNMNNNNNNNNNPMNPNNPMMNMMMNNNNNMNNMXNNNNNMXNN"
    "NPNNPXPPPPNNNPMMNMMMNNNMNPNPMPXNNNXNPNXNMXNNNPNNPMNMMPPPMPMMXXMXMPPPNPNMNNNNNXPX"
    "NNMPXMMNNNNNMPMXMNPNNXXPMPMPMNXNXPXXXNPXMNNNNXPNNNNNNNNNMMNNPNXMPPXPPPMPPNPPNNMN"
    "MPXPNNNNNMPMPNNNPPMMNNXMXNPXXX"
)


# Endpoint-changing decisions receive a concise mechanism tag so the final
# analysis can distinguish semantic failures from mere fine-taxonomy movement.
# IDs not present here stayed on the same accepted/non-accepted side.
CONSENSUS_SWEEP_ENDPOINT_FLIP_MECHANISMS = {
    "S0140": "restore_compatible_stemi_equivalent_parent",
    "S0147": "false_parent_distinct_dermatosis",
    "S0157": "conflicting_anatomic_site",
    "S0195": "false_family_distinct_colitis_etiology",
    "S0196": "unsupported_sepsis_and_graft_etiology",
    "S0199": "manifestation_only",
    "S0231": "manifestation_only",
    "S0236": "conflicting_nephritis_etiology",
    "S0264": "conflicting_traumatic_state",
    "S0290": "manifestation_only",
    "S0304": "restore_historical_alias_missing_metastatic_scope",
    "S0312": "distinct_tumor_histology",
    "S0315": "distinct_tumor_histology",
    "S0317": "nonspecific_differential_not_parent",
    "S0327": "conflicting_disease_state",
    "S0403": "unsupported_inflammatory_subtype",
    "S0411": "manifestation_only",
    "S0412": "manifestation_only",
    "S0414": "manifestation_only",
    "S0437": "restore_broader_parent_missing_keloidal_variant",
    "S0442": "distinct_neurologic_syndrome",
    "S0444": "conflicting_vascular_mechanism",
    "S0471": "distinct_tumor_histology",
    "S0506": "conflicting_hematologic_lineage",
    "S0508": "conflicting_hematologic_lineage",
    "S0511": "distinct_tumor_histology",
    "S0552": "distinct_retinal_entity",
    "S0651": "nonspecific_manifestation_not_parent",
    "S0666": "distinct_tumor_histology",
    "S0673": "distinct_tumor_histology",
    "S0674": "distinct_tumor_histology",
    "S0709": "distinct_entity",
    "S0712": "manifestation_only",
    "S0724": "manifestation_only",
    "S0725": "manifestation_only",
    "S0726": "manifestation_only",
    "S0730": "conflicting_hematologic_lineage",
    "S0756": "distinct_tumor_histology",
    "S0757": "distinct_tumor_histology",
    "S0758": "distinct_tumor_histology",
    "S0782": "distinct_tumor_histology",
    "S0795": "distinct_tumor_histology",
    "S0796": "distinct_tumor_histology",
    "S0797": "distinct_tumor_histology",
    "S0835": "conflicting_hematologic_lineage",
    "S0844": "distinct_tumor_histology",
    "S0845": "distinct_tumor_histology",
    "S0857": "manifestation_only",
    "S0868": "distinct_entity",
    "S0872": "nonspecific_differential_not_parent",
    "S0891": "distinct_entity",
    "S0892": "distinct_entity",
    "S0893": "distinct_entity",
    "S0896": "complication_only",
    "S0912": "distinct_tumor_histology",
    "S0913": "distinct_tumor_histology",
    "S0915": "distinct_tumor_histology",
    "S0921": "manifestation_only",
    "S0937": "nonspecific_differential_not_parent",
    "S0939": "manifestation_only",
    "S0940": "manifestation_only",
    "S0943": "nonspecific_differential_not_parent",
    "S0953": "distinct_entity",
    "S0954": "distinct_entity",
    "S0956": "distinct_tumor_histology",
    "S0962": "distinct_entity",
    "S0983": "conflicting_etiology",
    "S0991": "unsupported_malignant_transformation",
    "S1005": "distinct_tumor_histology",
    "S1015": "distinct_tumor_histology",
    "S1016": "distinct_tumor_histology",
    "S1059": "manifestation_only",
    "S1060": "manifestation_only",
}
