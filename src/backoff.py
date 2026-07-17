"""
Shared poll-loop backoff.

During a GitHub outage (503 storms) three agents polling every 15s keep a
pointlessly aggressive request rate for hours. Exponential backoff makes
the loops polite: base interval on success, doubling on consecutive
failures up to a cap, instant reset on the first success.
"""

DEFAULT_CAP_SECONDS = 900  # 15 min — outages are usually minutes-to-an-hour


def backoff_seconds(consecutive_failures: int, base: int,
                    cap: int = DEFAULT_CAP_SECONDS) -> int:
    """Sleep duration for a poll loop given how many cycles failed in a row.

    0 failures → base; then base*2, base*4, ... capped at `cap`.
    """
    if consecutive_failures <= 0:
        return base
    # Cap the exponent so huge failure counts can't overflow.
    factor = 2 ** min(consecutive_failures, 20)
    return min(base * factor, cap)
