# SPDX-License-Identifier: AGPL-3.0-or-later
"""Brasil de Todos — E2E Test Suite Runner.

Supports filtering by tier (--tier 1..4), generating TAP and Markdown outputs,
and returns exit code 0 on all pass / skip, nonzero on any failure.
"""
from __future__ import annotations

import argparse
import importlib
import inspect
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class TestResult:
    name: str
    tier: int
    feature: str
    status: str  # "PASS", "FAIL", "SKIP"
    duration: float
    error_message: str = ""
    traceback_text: str = ""


@dataclass
class SuiteSummary:
    results: list[TestResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "PASS")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "SKIP")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "FAIL")

    @property
    def pass_rate(self) -> float:
        evaluated = self.passed + self.failed
        return (self.passed / evaluated * 100.0) if evaluated > 0 else 100.0

    def tier_summary(self, tier: int) -> tuple[int, int, int, int, float]:
        tier_results = [r for r in self.results if r.tier == tier]
        tot = len(tier_results)
        pas = sum(1 for r in tier_results if r.status == "PASS")
        skp = sum(1 for r in tier_results if r.status == "SKIP")
        fld = sum(1 for r in tier_results if r.status == "FAIL")
        ev = pas + fld
        rate = (pas / ev * 100.0) if ev > 0 else (100.0 if skp > 0 else 0.0)
        return tot, pas, skp, fld, rate


def load_tier_module(tier: int):
    module_names = {
        1: "tests_e2e.test_tier1_features",
        2: "tests_e2e.test_tier2_boundaries",
        3: "tests_e2e.test_tier3_interactions",
        4: "tests_e2e.test_tier4_scenarios",
    }
    name = module_names.get(tier)
    if not name:
        return None
    try:
        return importlib.import_module(name)
    except Exception as exc:
        print(f"ERROR: Could not import {name}: {exc}")
        traceback.print_exc()
        return None


def discover_tests(tier: int) -> list[tuple[str, callable]]:
    mod = load_tier_module(tier)
    if not mod:
        return []
    tests = []
    for attr_name in dir(mod):
        if attr_name.startswith("test_"):
            fn = getattr(mod, attr_name)
            if callable(fn):
                tests.append((attr_name, fn))
    # Preserve definition / alphanumeric order
    tests.sort(key=lambda t: t[0])
    return tests


def extract_feature_key(test_name: str) -> str:
    parts = test_name.split("_")
    # e.g. test_tier1_f01_obrasgov_... -> f01_obrasgov
    if len(parts) >= 4 and parts[1].startswith("tier"):
        return f"{parts[2]}_{parts[3]}"
    return "general"


def run_single_test(test_name: str, fn: callable, tier: int) -> TestResult:
    feature_key = extract_feature_key(test_name)
    t0 = time.perf_counter()
    try:
        # Check if function takes arguments (like fixtures in pytest)
        sig = inspect.signature(fn)
        if len(sig.parameters) == 0:
            fn()
        else:
            # If function expects args, attempt no-arg call or handle gracefully
            fn()
        elapsed = time.perf_counter() - t0
        return TestResult(name=test_name, tier=tier, feature=feature_key, status="PASS", duration=elapsed)
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        exc_type = type(exc).__name__
        msg = str(exc)
        # Check if it was skipped
        if exc_type in ("Skipped", "SkipTest") or "skip" in msg.lower() and "milestone" in msg.lower():
            return TestResult(name=test_name, tier=tier, feature=feature_key, status="SKIP", duration=elapsed, error_message=msg)
        return TestResult(
            name=test_name,
            tier=tier,
            feature=feature_key,
            status="FAIL",
            duration=elapsed,
            error_message=f"{exc_type}: {msg}",
            traceback_text=traceback.format_exc(),
        )


def format_tap(summary: SuiteSummary) -> str:
    lines = ["TAP version 13", f"1..{summary.total}"]
    for idx, r in enumerate(summary.results, 1):
        if r.status == "PASS":
            lines.append(f"ok {idx} - {r.name} ({r.duration:.3f}s)")
        elif r.status == "SKIP":
            lines.append(f"ok {idx} - {r.name} # SKIP {r.error_message}")
        else:
            lines.append(f"not ok {idx} - {r.name} ({r.duration:.3f}s)")
            lines.append(f"  ---")
            lines.append(f"  message: {r.error_message}")
            lines.append(f"  severity: fail")
            lines.append(f"  ...")
    return "\n".join(lines)


def format_markdown(summary: SuiteSummary) -> str:
    lines = [
        "# E2E Test Execution Report — Brasil de Todos",
        "",
        f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime())}  ",
        f"**Total Tests**: {summary.total} | **Passed**: {summary.passed} | **Skipped**: {summary.skipped} | **Failed**: {summary.failed}  ",
        f"**Pass Rate**: {summary.pass_rate:.1f}% | **Duration**: {summary.end_time - summary.start_time:.2f}s  ",
        "",
        "## Summary by Tier",
        "",
        "| Tier | Name | Total | Passed | Skipped | Failed | Pass Rate |",
        "|:----:|------|:-----:|:------:|:-------:|:------:|:---------:|",
    ]

    tier_names = {
        1: "Tier 1: Feature Coverage (min 5/feature)",
        2: "Tier 2: Boundary & Negative Cases",
        3: "Tier 3: Cross-Feature Interactions",
        4: "Tier 4: Real-World Scenarios",
    }

    for tier in (1, 2, 3, 4):
        tot, pas, skp, fld, rate = summary.tier_summary(tier)
        if tot > 0:
            lines.append(f"| {tier} | {tier_names[tier]} | {tot} | {pas} | {skp} | {fld} | {rate:.1f}% |")

    lines.append(f"| **All** | **Total Suite** | **{summary.total}** | **{summary.passed}** | **{summary.skipped}** | **{summary.failed}** | **{summary.pass_rate:.1f}%** |")
    lines.append("")

    if summary.failed > 0:
        lines.append("## Failed Tests")
        lines.append("")
        for r in summary.results:
            if r.status == "FAIL":
                lines.append(f"### ❌ `{r.name}` (Tier {r.tier})")
                lines.append(f"- **Error**: `{r.error_message}`")
                lines.append("```")
                lines.append(r.traceback_text.strip())
                lines.append("```")
                lines.append("")

    if summary.skipped > 0:
        lines.append("## Skipped Tests (Progressive Milestones Pending)")
        lines.append("")
        for r in summary.results:
            if r.status == "SKIP":
                lines.append(f"- ⏳ `{r.name}`: {r.error_message}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Brasil de Todos E2E Test Suite Runner")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4], help="Run only tests from a specific tier (1, 2, 3, or 4)")
    parser.add_argument("--tap", action="store_true", help="Output in TAP version 13 format")
    parser.add_argument("--md", action="store_true", help="Output Markdown report to stdout")
    parser.add_argument("--output-md", type=str, help="Save Markdown report to designated file path")
    parser.add_argument("--output-tap", type=str, help="Save TAP report to designated file path")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose test execution logging")
    args = parser.parse_args()

    selected_tiers = [args.tier] if args.tier else [1, 2, 3, 4]

    summary = SuiteSummary()
    summary.start_time = time.perf_counter()

    print("=" * 70)
    print("  Brasil de Todos — E2E Test Suite Execution")
    print("=" * 70)

    for tier in selected_tiers:
        tier_tests = discover_tests(tier)
        print(f"\n---> Running Tier {tier} ({len(tier_tests)} tests discovered)...")
        for name, fn in tier_tests:
            res = run_single_test(name, fn, tier)
            summary.results.append(res)
            if args.verbose or res.status != "PASS":
                mark = "OK" if res.status == "PASS" else ("SKIP" if res.status == "SKIP" else "FAIL")
                note = f" [{res.error_message}]" if res.status != "PASS" else ""
                print(f"  [{mark:<4}] {res.status:<4} {res.name:<55} ({res.duration:.3f}s){note}")
            else:
                sys.stdout.write(".")
                sys.stdout.flush()
        print()

    summary.end_time = time.perf_counter()

    print("\n" + "=" * 70)
    print("  E2E Test Execution Summary")
    print("=" * 70)
    print(f"  Total Tests : {summary.total}")
    print(f"  Passed      : {summary.passed}")
    print(f"  Skipped     : {summary.skipped}")
    print(f"  Failed      : {summary.failed}")
    print(f"  Pass Rate   : {summary.pass_rate:.1f}%")
    print(f"  Duration    : {summary.end_time - summary.start_time:.2f}s")
    print("=" * 70)

    if args.tap:
        tap_text = format_tap(summary)
        print("\n" + tap_text)

    if args.md:
        md_text = format_markdown(summary)
        print("\n" + md_text)

    if args.output_md:
        out_path = Path(args.output_md)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(format_markdown(summary), encoding="utf-8")
        print(f"Markdown report written to: {out_path}")

    if args.output_tap:
        out_path = Path(args.output_tap)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(format_tap(summary), encoding="utf-8")
        print(f"TAP report written to: {out_path}")

    # Return code 0 when no failures (passes + skips only), nonzero if failures
    sys.exit(0 if summary.failed == 0 else 1)


if __name__ == "__main__":
    main()
