"""Panel removals requested by site owners.

The crawler page tells a site owner they can ask to be left out, and that the
removal is recorded with its reason. These tests exist because that was a
published promise resting on an operator's memory, with nothing in the code
behind it.

The property worth most attention is that honouring one promise must not break
another: the panel is the denominator of every published figure, so a removal
has to change future periods without restating past ones.
"""

import json

import pytest

from tallyhouse.config import Removal, load_removals, removals_in_effect

NEXT = "2026-10-05"


def write_removals(root, entries):
    path = root / "panel" / "removals.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"removals": entries}))


def entry(domain="example.com", effective_from=NEXT, **over):
    base = {"domain": domain, "effective_from": effective_from,
            "reason": "Owner asked to be excluded.", "requested": "2026-10-01",
            "source": "https://github.com/allanderek/tallyhouse/issues/1"}
    base.update(over)
    return base


def test_a_removal_loads_with_its_reason_and_date(tmp_path):
    write_removals(tmp_path, [entry()])
    removals = load_removals(tmp_path)
    assert removals == [Removal(
        domain="example.com", effective_from=NEXT,
        reason="Owner asked to be excluded.", requested="2026-10-01",
        source="https://github.com/allanderek/tallyhouse/issues/1",
    )]


def test_no_removals_file_is_not_an_error(tmp_path):
    assert load_removals(tmp_path) == []


def test_a_removal_without_a_reason_is_refused(tmp_path):
    # Indistinguishable from a quiet edit to the denominator.
    write_removals(tmp_path, [entry(reason="")])
    with pytest.raises(ValueError, match="reason"):
        load_removals(tmp_path)


def test_a_removal_without_an_effective_period_is_refused(tmp_path):
    # Cannot be applied without deciding, silently, which published prints to
    # restate.
    write_removals(tmp_path, [entry(effective_from="")])
    with pytest.raises(ValueError, match="effective_from"):
        load_removals(tmp_path)


def test_a_domain_listed_twice_is_refused(tmp_path):
    write_removals(tmp_path, [entry(), entry(effective_from="2026-10-12")])
    with pytest.raises(ValueError, match="more than once"):
        load_removals(tmp_path)


def test_a_removal_does_not_apply_before_its_effective_period(tmp_path):
    """The property that keeps published numbers re-derivable.

    Without it, honouring a request would change the denominator of every print
    that ever included the domain -- restating numbers the ledger promises never
    to change silently.
    """
    write_removals(tmp_path, [entry(effective_from="2026-10-05")])
    removals = load_removals(tmp_path)
    assert removals_in_effect(removals, "2026-09-28") == set()
    assert removals_in_effect(removals, "2026-10-05") == {"example.com"}
    assert removals_in_effect(removals, "2026-10-12") == {"example.com"}


def test_removals_accumulate_over_periods(tmp_path):
    write_removals(tmp_path, [
        entry("a.com", effective_from="2026-10-05"),
        entry("b.com", effective_from="2026-10-12"),
    ])
    removals = load_removals(tmp_path)
    assert removals_in_effect(removals, "2026-10-05") == {"a.com"}
    assert removals_in_effect(removals, "2026-10-12") == {"a.com", "b.com"}
