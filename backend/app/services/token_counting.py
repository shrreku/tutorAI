import re


_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def approximate_token_count(text: str) -> int:
    """Deterministic fallback token estimate that does not require network access."""
    pieces = _TOKEN_PATTERN.findall(text or "")
    if not pieces:
        return 0

    return max(1, int(len(pieces) * 1.25))
