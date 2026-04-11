#!/usr/bin/env python3
"""Simple retry wrapper for flaky API calls.

Usage:
    from bigclaw_retry import retry
    data = retry(lambda: yf.download("TSLA", period="1d"), attempts=3, delay=2)
"""

import time
from bigclaw_logging import get_logger

log = get_logger("retry")


def retry(fn, attempts=2, delay=3, label="API call"):
    """Call fn(), retrying on exception up to `attempts` times.

    Returns the result on success, or re-raises the last exception.
    """
    last_err = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if i < attempts:
                log.warning(f"{label} attempt {i}/{attempts} failed: {e} — retrying in {delay}s")
                time.sleep(delay)
            else:
                log.error(f"{label} failed after {attempts} attempts: {e}")
    raise last_err
