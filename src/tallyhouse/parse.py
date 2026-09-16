"""Classification of a robots.txt body into a stance per agent.

Stance is defined operationally by a fixed probe set rather than by reading
directives directly. This is robust to the many ways a real file can express
the same policy, and it is reproducible — but it means PROBE_PATHS is part of
the published methodology, not an implementation detail.
"""

import re

from protego import Protego

from tallyhouse.constants import PROBE_BASE, PROBE_PATHS

# An agent token no real site will name, used to observe the "*" group.
_BLANKET_PROBE_AGENT = "TallyhouseBlanketProbe"

_USER_AGENT_LINE = re.compile(r"^\s*user-agent\s*:\s*(.+?)\s*$", re.IGNORECASE)


def is_mentioned(body: str, agent: str) -> bool:
    """True if the agent is named in a User-agent line.

    Matching is exact and case-insensitive on the whole token, so that
    "Applebot-Extended" does not imply "Applebot".
    """
    wanted = agent.lower()
    for line in body.splitlines():
        match = _USER_AGENT_LINE.match(line)
        if match and match.group(1).lower() == wanted:
            return True
    return False


def _stance_from_probes(body: str, agent: str) -> str:
    parser = Protego.parse(body)
    results = [parser.can_fetch(PROBE_BASE + path, agent) for path in PROBE_PATHS]
    if not any(results):
        return "FullBlock"
    if all(results):
        return "Allowed"
    return "PartialBlock"


def classify(body: str, agent: str) -> str:
    """The stance a site takes toward a specific named agent.

    An agent the file never names is Unmentioned even when a blanket "*" rule
    blocks it, because the targeted headline measures deliberate stance toward
    that agent. Blanket blocking is reported separately by blanket_stance.
    """
    if not is_mentioned(body, agent):
        return "Unmentioned"
    return _stance_from_probes(body, agent)


def blanket_stance(body: str) -> str:
    """The stance the "*" group takes, observed via an unnamed agent."""
    return _stance_from_probes(body, _BLANKET_PROBE_AGENT)
