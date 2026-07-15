"""Spintax rendering for message evasion.

``Hey {there|hi|hello}`` -> one variant chosen at random. Nested groups are
resolved innermost-first so no two rendered messages need be identical.
"""

import random
import re

_GROUP = re.compile(r"\{([^{}]*)\}")


def spin(text: str, rng: random.Random | None = None) -> str:
    rng = rng or random
    result = text
    # Resolve innermost {a|b|c} groups repeatedly until none remain.
    while True:
        match = _GROUP.search(result)
        if not match:
            break
        options = match.group(1).split("|")
        result = result[: match.start()] + rng.choice(options) + result[match.end():]
    return result
