"""NFR-004 (performance) and NFR-005 (stdlib-only core); other NFRs are harness gates."""
from __future__ import annotations

import ast
import sys
import time
from pathlib import Path

from ratelimiter.config import DEFAULT_TIERS
from ratelimiter.limiter import RateLimiter

CORE_MODULES = ["errors.py", "config.py", "limiter.py", "store.py"]
SRC_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "ratelimiter"


def test_nfr_004_ten_thousand_checks_finish_under_two_seconds(clock):
    limiter = RateLimiter(DEFAULT_TIERS, clock=clock)
    started = time.perf_counter()
    for i in range(10_000):
        limiter.check(f"client-{i % 100}", "enterprise")
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0, f"expected: < 2.0s | observed: {elapsed:.3f}s for 10,000 checks"


def test_nfr_005_core_modules_import_only_the_standard_library():
    offenders = []
    for name in CORE_MODULES:
        tree = ast.parse((SRC_PACKAGE / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            roots = []
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots = [node.module.split(".")[0]]
            offenders += [
                f"{name}: {root}" for root in roots if root not in sys.stdlib_module_names
            ]
    assert not offenders, f"expected: stdlib-only imports | observed third-party: {offenders}"
