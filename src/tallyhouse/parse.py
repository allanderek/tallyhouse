"""Classification of a robots.txt body into a stance per agent.

Stance is determined by:
- FullBlock: all probe paths blocked (probe-based, methodology-consistent)
- PartialBlock: agent's group has effective Disallow directives (directive-based,
  catches real partial blocks on common paths like /articles, /premium)
- Allowed: agent named but no effective blocks
- Unmentioned: agent never named (even if blanket "*" blocks it)

This hybrid approach uses probes for FullBlock/Allowed decisions (robust and
reproducible) and directives for PartialBlock (detects targeting at any path).
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


def _agent_matches_token(agent: str, token: str) -> bool:
    """Check if agent matches a token (case-insensitive, whole-token)."""
    return agent.lower() == token.lower()


def _parse_groups(body: str) -> list[tuple[list[str], list[tuple[str, str]]]]:
    """Parse robots.txt into (agent_tokens, rules) groups per RFC 9309.

    Consecutive User-agent lines form one group; a new User-agent line after
    rules starts a new group. Returns list of (agent_list, rules_list) tuples.
    """
    groups = []
    current_agents = []
    current_rules = []

    for line in body.splitlines():
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith('#'):
            continue

        # Parse the line
        if ':' not in line:
            continue

        directive, value = line.split(':', 1)
        directive = directive.strip().lower()
        value = value.strip()

        if directive == 'user-agent':
            # Check if we're starting a new group (non-consecutive User-agent)
            if current_rules:
                # We've seen rules, so a new User-agent line starts a new group
                groups.append((current_agents, current_rules))
                current_agents = [value]
                current_rules = []
            else:
                # Accumulate consecutive User-agents
                current_agents.append(value)
        elif directive in ('allow', 'disallow'):
            # Accumulate rules
            current_rules.append((directive, value))

    # Close the last group
    if current_agents:
        groups.append((current_agents, current_rules))

    return groups


def _sanitize_disallow_pattern(pattern: str) -> str:
    """Sanitize a Disallow pattern for use as a test path.

    Drop trailing $ (not valid in paths) and replace * with / (literal segment).
    """
    if pattern.endswith('$'):
        pattern = pattern[:-1]
    pattern = pattern.replace('*', '/')
    return pattern


def _agent_has_effective_disallow(body: str, agent: str, parser: Protego) -> bool:
    """Check if agent's groups contain at least one effective Disallow.

    An effective Disallow is one that protego confirms blocks the agent
    (accounting for Allow overrides). If sanitisation makes the pattern
    unusable, count it as partial block (safer for index accuracy).
    """
    groups = _parse_groups(body)

    for agent_tokens, rules in groups:
        # Check if target agent is in this group
        if not any(_agent_matches_token(agent, token) for token in agent_tokens):
            continue

        # Check each rule in this group
        for directive, value in rules:
            if directive == 'disallow' and value:  # Non-empty Disallow
                # Sanitize the pattern for testing
                path = _sanitize_disallow_pattern(value)
                if not path:
                    # Sanitisation left it empty; count as partial block (safer)
                    return True
                # Ask protego: does it actually block this path?
                if not parser.can_fetch(PROBE_BASE + path, agent):
                    return True

    return False


def classify(body: str, agent: str) -> str:
    """The stance a site takes toward a specific named agent.

    An agent the file never names is Unmentioned even when a blanket "*" rule
    blocks it, because the targeted headline measures deliberate stance toward
    that agent. Blanket blocking is reported separately by blanket_stance.

    Stance is determined by:
    1. Agent not mentioned -> Unmentioned
    2. All probe paths blocked -> FullBlock (probe-based)
    3. Agent's group has effective Disallow -> PartialBlock (directive-based)
    4. Else -> Allowed
    """
    # Step 1: Agent not mentioned -> Unmentioned
    if not is_mentioned(body, agent):
        return "Unmentioned"

    # Parse once for efficiency
    parser = Protego.parse(body)

    # Step 2: All probe paths blocked -> FullBlock
    results = [parser.can_fetch(PROBE_BASE + path, agent) for path in PROBE_PATHS]
    if not any(results):
        return "FullBlock"

    # Step 3: Has effective Disallow in agent's group -> PartialBlock
    if _agent_has_effective_disallow(body, agent, parser):
        return "PartialBlock"

    # Step 4: Allowed
    return "Allowed"


def blanket_stance(body: str) -> str:
    """The stance the "*" group takes, observed via an unnamed agent.

    Uses probe-based classification (unchanged from original) because the
    blanket rule applies to all agents, not targeting a specific one.
    """
    parser = Protego.parse(body)
    results = [parser.can_fetch(PROBE_BASE + path, _BLANKET_PROBE_AGENT) for path in PROBE_PATHS]
    if not any(results):
        return "FullBlock"
    if all(results):
        return "Allowed"
    return "PartialBlock"
