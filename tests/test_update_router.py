from agentclinic_tree_dx.update_router import choose_update_method


def test_update_method_priority():
    assert choose_update_method({"calculator_applicable": True}) == "calculator"
    assert choose_update_method({"formal_rule_available": True}) == "rule_based"
    assert choose_update_method({}) == "ordinal"
