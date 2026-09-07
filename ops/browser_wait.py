# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bounded host-side polling for browser timing tests, without unsafe-eval.

Only the two counters created by the test timing shim are readable. This helper
never changes the application's CSP or substitutes responses from its API.
"""
from __future__ import annotations

import math
import time
from typing import Protocol


class CounterPage(Protocol):
    def evaluate(self, expression: str, arg: str) -> object: ...
    def wait_for_timeout(self, timeout: float) -> None: ...


def wait_for_counter(page: CounterPage, key: str, expected: int,
                     timeout_ms: float = 10000) -> None:
    """Wait for exactly the expected number of actual API responses.

    Poll from Python rather than Playwright's wait_for_function, which compiles
    its string predicate inside the page and is refused by strict script-src.
    Playwright evaluation uses the browser protocol; no policy bypass is needed.
    """
    if key not in ('__received', '__released'):
        raise ValueError('unsupported_browser_counter')
    if type(expected) is not int or expected < 0:
        raise ValueError('invalid_browser_counter_target')
    if (type(timeout_ms) not in (int, float) or not math.isfinite(timeout_ms)
            or not 0 < timeout_ms <= 30000):
        raise ValueError('invalid_browser_counter_timeout')
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        actual = page.evaluate('(key) => window[key]', key)
        if type(actual) is not int or actual < 0:
            raise AssertionError('invalid_browser_counter_value')
        if actual == expected:
            return
        if actual > expected:
            raise AssertionError('browser_counter_exceeded_target')
        remaining_ms = (deadline - time.monotonic()) * 1000
        if remaining_ms <= 0:
            raise TimeoutError(f'browser_counter_timeout:{key}:{actual}/{expected}')
        # Pump browser events while retaining a bounded deadline.
        page.wait_for_timeout(min(25, remaining_ms))
