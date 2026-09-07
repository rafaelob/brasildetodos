# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression tests of the test-only polling helper, not production mocks."""
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ops'))
from browser_wait import wait_for_counter
import browser_wait


class Page:
    def __init__(self, values):
        self.values = iter(values)
        self.waits = []
        self.reads = []

    def evaluate(self, expression, key):
        self.reads.append((expression, key))
        return next(self.values)

    def wait_for_timeout(self, value):
        self.waits.append(value)


def test_wait_observes_exact_response_count_without_eval():
    page = Page([0, 1, 2])
    wait_for_counter(page, '__received', 2)
    assert len(page.waits) == 2
    assert page.reads == [('(key) => window[key]', '__received')] * 3


def test_already_released_has_no_delay():
    page = Page([2])
    wait_for_counter(page, '__released', 2)
    assert page.waits == []


@pytest.mark.parametrize('actual', [None, True, -1, 2.5, '2'])
def test_invalid_counter_does_not_report_success(actual):
    with pytest.raises(AssertionError, match='invalid_browser_counter_value'):
        wait_for_counter(Page([actual]), '__received', 2)


def test_extra_response_is_not_hidden_by_greater_than_comparison():
    with pytest.raises(AssertionError, match='exceeded_target'):
        wait_for_counter(Page([3]), '__received', 2)


def test_timeout_is_bounded(monkeypatch):
    clock = iter([0, .01, .02])
    monkeypatch.setattr(browser_wait.time, 'monotonic', lambda: next(clock))
    page = Page([0, 1])
    with pytest.raises(TimeoutError, match='__received:1/2'):
        wait_for_counter(page, '__received', 2, timeout_ms=15)
    assert page.waits == [pytest.approx(5)]


@pytest.mark.parametrize('timeout', [0, -1, True, float('inf'), float('nan'), 30001])
def test_invalid_timeout_rejected_before_browser_access(timeout):
    page = Page([])
    with pytest.raises(ValueError, match='timeout'):
        wait_for_counter(page, '__received', 2, timeout)
    assert not page.reads


@pytest.mark.parametrize('target', [-1, True, '2', 1.5])
def test_invalid_target_rejected(target):
    with pytest.raises(ValueError, match='target'):
        wait_for_counter(Page([]), '__received', target)


def test_no_arbitrary_javascript_or_property_lookup():
    with pytest.raises(ValueError, match='unsupported'):
        wait_for_counter(Page([]), 'localStorage', 0)


def test_page_execution_failure_is_not_swallowed():
    class ClosedPage(Page):
        def evaluate(self, expression, key):
            raise RuntimeError('page_closed')
    with pytest.raises(RuntimeError, match='page_closed'):
        wait_for_counter(ClosedPage([]), '__received', 2)


def test_lifecycle_uses_host_polling_and_keeps_security_policy():
    text = (ROOT / 'ops/browser_detail_lifecycle.py').read_text()
    assert 'page.wait_for_function(' not in text
    assert "wait_for_counter(page,'__received',2)" in text
    assert "wait_for_counter(page,'__released',2)" in text
    assert 'bypass_csp' not in text
    assert 'unsafe-eval' not in text
