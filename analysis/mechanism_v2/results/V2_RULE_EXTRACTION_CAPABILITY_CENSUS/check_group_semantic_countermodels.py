#!/usr/bin/env python3
"""Check bounded Boolean/arithmetic witnesses, not clinical correctness or production behavior."""
import json
from itertools import product
from pathlib import Path


def main():
    panel_path = Path(__file__).with_name('group_semantic_panel.json')
    panel = json.loads(panel_path.read_text())
    assert len(panel['cases']) == 8
    assert len({case['source_rule_id'] for case in panel['cases']}) == 8
    checks = {
        'alvarado_low_example': 2 + 1 == 3,
        'alvarado_equal_count_different_weights': 2 + 2 == 4 and 1 + 1 == 2,
        'catatonia_qualifier_completion': sum([True and not True, True, True, False]) == 2
        and sum([True, True, True, False]) == 3,
        'ICM_definition_vs_projection': not all([True, False, False])
        and all([True, True, True])
        and [True][0] == [True][0],
        'light_chain_mixed_cells': not (
            all(cell == 'kappa' for cell in ['kappa', 'lambda'])
            or all(cell == 'lambda' for cell in ['kappa', 'lambda'])
        ),
        'EEG_literal_negation': not False,
        'OR_flattening': all(((a or b) or c) == (a or b or c) for a, b, c in product([False, True], repeat=3)),
    }
    assert all(checks.values())
    assert checks == panel['deterministic_boolean_arithmetic_checks']
    print(json.dumps({'checks_passed': len(checks), 'scope': 'symbolic witnesses only', 'checks': checks}, indent=2))


if __name__ == '__main__':
    main()
