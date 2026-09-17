"""Index computation. A pure function of classified tables — no I/O, no
network, no clock."""

from tallyhouse.constants import CONCLUSIVE_OUTCOMES

_BLOCKING_STANCES = frozenset({"FullBlock", "PartialBlock"})


def conclusive_domains(observations: list[dict]) -> set[str]:
    return {
        o["domain"] for o in observations if o["outcome"] in CONCLUSIVE_OUTCOMES
    }


def coverage(observations: list[dict], panel_size: int) -> float:
    if panel_size == 0:
        raise ValueError("panel_size must be positive")
    return _pct(len(conclusive_domains(observations)), panel_size)


def _pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        raise ValueError("no conclusive observations to compute a rate over")
    return round(100.0 * numerator / denominator, 4)


def _targeted_domains(verdicts: list[dict], conclusive: set[str]) -> set[str]:
    return {
        v["domain"]
        for v in verdicts
        if v["domain"] in conclusive and v["stance"] in _BLOCKING_STANCES
    }


def targeted_rate(verdicts: list[dict], conclusive: set[str]) -> float:
    return _pct(len(_targeted_domains(verdicts, conclusive)), len(conclusive))


def blanket_blocked(blanket: dict[str, str], conclusive: set[str]) -> set[str]:
    """Return domains blanket-blocked to all crawlers (User-agent: *).

    Only FullBlock counts, not PartialBlock. For named agents, any disallow
    signals intent toward that crawler. For the wildcard group, only total
    closure counts as a stance toward AI; partial rules are ordinary site
    hygiene (e.g. Disallow: /wp-admin/) and not evidence of intent.
    """
    return {d for d, stance in blanket.items() if d in conclusive and stance == "FullBlock"}


def blanket_rate(blanket: dict[str, str], conclusive: set[str]) -> float:
    return _pct(len(blanket_blocked(blanket, conclusive)), len(conclusive))


def effective_rate(
    verdicts: list[dict], blanket: dict[str, str], conclusive: set[str]
) -> float:
    blocked = _targeted_domains(verdicts, conclusive) | blanket_blocked(blanket, conclusive)
    return _pct(len(blocked), len(conclusive))


def per_agent_rates(verdicts: list[dict], conclusive: set[str]) -> dict[str, float]:
    agents = sorted({v["agent"] for v in verdicts})
    rates = {}
    for agent in agents:
        blocking = {
            v["domain"]
            for v in verdicts
            if v["agent"] == agent
            and v["domain"] in conclusive
            and v["stance"] in _BLOCKING_STANCES
        }
        rates[agent] = _pct(len(blocking), len(conclusive))
    return rates


def like_for_like_change(
    prev_verdicts: list[dict],
    prev_conclusive: set[str],
    cur_verdicts: list[dict],
    cur_conclusive: set[str],
) -> float | None:
    """Week-on-week change over domains conclusively observed in both weeks.

    At weekly cadence the true movements are small, so a denominator that
    wobbles between periods could otherwise manufacture a change that never
    happened. Returns None when there is no comparable previous period.
    """
    both = prev_conclusive & cur_conclusive
    if not both:
        return None
    return round(targeted_rate(cur_verdicts, both) - targeted_rate(prev_verdicts, both), 4)
