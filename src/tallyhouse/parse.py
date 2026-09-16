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

from protego import Protego

from tallyhouse.constants import PROBE_BASE, PROBE_PATHS

# An agent token no real site will name, used to observe the "*" group.
_BLANKET_PROBE_AGENT = "TallyhouseBlanketProbe"


def _strip_comment(line: str) -> str:
    """Strip comment (everything from # onwards) from a line per RFC 9309.

    Comments begin at the first unquoted # and extend to end of line.
    After removing the comment, strip surrounding whitespace.
    """
    # Find the first # (RFC 9309 doesn't use quoted strings)
    idx = line.find('#')
    if idx >= 0:
        line = line[:idx]
    return line.strip()


def _parse_directive_line(line: str) -> tuple[str, str] | None:
    """Parse a directive line: strip comment, extract directive and value.

    Returns (directive_lowercase, value_stripped) or None if line is empty
    or invalid. This is the single source of truth for directive extraction,
    used by both is_mentioned() and _parse_groups() so they cannot drift
    in their interpretation of comments.
    """
    line = _strip_comment(line)

    if not line or ':' not in line:
        return None

    directive, value = line.split(':', 1)
    return (directive.strip().lower(), value.strip())


def is_mentioned(body: str, agent: str) -> bool:
    """True if the agent is named in a User-agent line.

    Matching is exact and case-insensitive on the whole token, so that
    "Applebot-Extended" does not imply "Applebot". Comments (# to EOL)
    are stripped per RFC 9309 before matching.
    """
    for line in body.splitlines():
        parsed = _parse_directive_line(line)
        if parsed and parsed[0] == 'user-agent':
            if _agent_matches_token(agent, parsed[1]):
                return True
    return False


def _agent_matches_token(agent: str, token: str) -> bool:
    """Check if agent matches a token (case-insensitive, whole-token)."""
    return agent.lower() == token.lower()


def _parse_groups(body: str) -> list[tuple[list[str], list[tuple[str, str]]]]:
    """Parse robots.txt into (agent_tokens, rules) groups per RFC 9309.

    Consecutive User-agent lines form one group; a User-agent line that follows
    ANY directive starts a new group. Comments (# to EOL) are stripped per RFC
    9309. Returns list of (agent_list, rules_list) tuples.

    "Consecutive" is judged against every directive, not only Allow/Disallow.
    Testing only for accumulated rules merged a named group whose body is
    entirely non-rule directives (Crawl-delay, Sitemap, Host) into the group
    that follows it, so

        User-agent: GPTBot
        Crawl-delay: 10
        User-agent: *
        Disallow: /

    read as one group naming both GPTBot and *, handing GPTBot a rule that
    belongs to the wildcard group and inviting the targeted headline to count a
    merely blanket-affected domain (spec 6.4).

    Rules appearing before any User-agent line belong to no group and are
    discarded, per RFC 9309.
    """
    groups = []
    current_agents = []
    current_rules = []
    seen_directive = False

    for line in body.splitlines():
        parsed = _parse_directive_line(line)

        if not parsed:
            # Empty, comment-only, or malformed line; skip
            continue

        directive, value = parsed

        if directive == 'user-agent':
            if seen_directive:
                # The current group has a body, so this line opens a new one.
                if current_agents:
                    groups.append((current_agents, current_rules))
                current_agents = [value]
                current_rules = []
                seen_directive = False
            else:
                # Accumulate consecutive User-agents
                current_agents.append(value)
        else:
            # Crawl-delay, Sitemap, Host and friends are not rules, but they do
            # close the run of User-agent lines that opened this group.
            seen_directive = True
            if directive in ('allow', 'disallow'):
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
    (accounting for Allow overrides). Protego is the only thing allowed to
    decide that a pattern blocks: a pattern this module cannot turn into a
    testable path is skipped rather than assumed to block, because asserting a
    block nobody confirmed puts a domain into the targeted headline numerator
    on the strength of a sanitisation failure.
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
                    # Nothing testable survives sanitisation (e.g. "Disallow: $",
                    # which matches only the empty path and so blocks nothing).
                    # Skip it: only protego may declare a block.
                    continue
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
