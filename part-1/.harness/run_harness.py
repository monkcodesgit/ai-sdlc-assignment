#!/usr/bin/env python3
"""Deterministic harness runner for Part 1A (Tiered Rate Limiter).

Stdlib only. Runs every gate, writes machine-readable results plus a feedback
file the coding agent can consume. Exit code 0 only if EVERY gate passes.

Usage:
    python .harness/run_harness.py          run all gates
    python .harness/run_harness.py --lock   (HUMAN ONLY) re-baseline integrity hashes

Gates (requirement they enforce):
    integrity       NFR-008  tests/harness/config files unchanged since human baseline
    lint            NFR-001  Ruff, zero violations
    sast            NFR-002  Bandit, zero MEDIUM/HIGH findings
    secrets         NFR-006  no secrets / .env / key files in the repo
    suppressions    NFR-007  no noqa / nosec / type-ignore comments in src/
    tests           AC-*     pytest + coverage >= 90 percent (NFR-003)
    traceability    all      every spec AC/NFR id has a test or an enforcing gate
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / ".harness"
RESULTS = ROOT / "evidence" / "harness-results"
LOCK_FILE = HARNESS / "integrity.lock.json"
TAIL_CHARS = 6000

PROTECTED_GLOBS = [
    "tests/**/*.py",
    "pytest.ini",
    "requirements-dev.txt",
    ".harness/*.py",
    ".harness/ruff.toml",
]

# Spec requirement ids that are enforced by a harness gate rather than a named test.
GATE_COVERED = {
    "NFR-001": "lint",
    "NFR-002": "sast",
    "NFR-003": "tests (coverage)",
    "NFR-006": "secrets",
    "NFR-007": "suppressions",
    "NFR-008": "integrity",
}

SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".ruff_cache",
    ".pytest_cache", "harness-results", "htmlcov",
}
SECRET_SELF_EXCLUDE = {".harness/run_harness.py"}
SECRET_PATTERNS = [
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("api-key-like", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    (
        "hardcoded-credential",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|passwd|password|token)\b\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']"
        ),
    ),
]
SUPPRESSION_RE = re.compile(r"#\s*(noqa|nosec|type:\s*ignore|ruff:|pylint:\s*disable)", re.I)


# --------------------------------------------------------------------------- helpers
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # CRLF-safe on Windows
    return hashlib.sha256(data).hexdigest()


def _tail(text: str) -> str:
    return text if len(text) <= TAIL_CHARS else "...[truncated]...\n" + text[-TAIL_CHARS:]


def _git_commit() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, check=False, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() or None if proc.returncode == 0 else None


def _new_gate(name: str, requirement: str, expected: str) -> dict:
    return {
        "name": name, "requirement": requirement, "status": "FAIL", "expected": expected,
        "observed": "", "command": None, "exit_code": None, "duration_s": 0.0,
        "output_tail": "", "details": [],
    }


def _finish(gate: dict, status: str, observed: str) -> dict:
    gate["status"] = status
    gate["observed"] = observed
    return gate


def _run(gate: dict, cmd: list[str]) -> subprocess.CompletedProcess | None:
    """Run a command; fill the gate's command/exit/duration/output. None if it cannot start."""
    gate["command"] = " ".join(cmd)
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=False, timeout=900,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        gate["duration_s"] = round(time.perf_counter() - started, 2)
        _finish(gate, "ERROR", f"could not execute command: {exc}")
        return None
    gate["duration_s"] = round(time.perf_counter() - started, 2)
    gate["exit_code"] = proc.returncode
    gate["output_tail"] = _tail((proc.stdout or "") + ("\n[stderr]\n" + proc.stderr if proc.stderr else ""))
    if proc.returncode != 0 and "No module named" in (proc.stderr or ""):
        _finish(gate, "ERROR", "tool not installed (environment problem, not an application failure): "
                "run `pip install -r requirements-dev.txt`")
        return None
    return proc


# --------------------------------------------------------------------------- integrity
def _protected_files() -> dict[str, str]:
    files: dict[str, str] = {}
    for pattern in PROTECTED_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path.is_file() and "__pycache__" not in path.parts:
                files[path.relative_to(ROOT).as_posix()] = _sha256(path)
    return files


def write_lock() -> int:
    files = _protected_files()
    LOCK_FILE.write_text(
        json.dumps({"created_utc": _now(), "files": files}, indent=2) + "\n", encoding="utf-8"
    )
    RESULTS.mkdir(parents=True, exist_ok=True)
    with (RESULTS / "baseline-changes.log").open("a", encoding="utf-8") as fh:
        fh.write(f"{_now()} baseline lock written: {len(files)} protected files, "
                 f"lock sha256={_sha256(LOCK_FILE)[:12]}, commit={_git_commit()}\n")
    print(f"Baseline written for {len(files)} protected files -> {LOCK_FILE.relative_to(ROOT)}")
    print("Review the diff in git and record WHY in evidence/harness-log.md.")
    return 0


def gate_integrity() -> dict:
    gate = _new_gate("integrity", "NFR-008",
                     "Protected files (tests, harness, configs) match the human-approved baseline.")
    if not LOCK_FILE.exists():
        return _finish(gate, "FAIL", "no baseline lock. A human must run: "
                       "python .harness/run_harness.py --lock")
    baseline = json.loads(LOCK_FILE.read_text(encoding="utf-8"))["files"]
    current = _protected_files()
    modified = sorted(p for p in baseline if p in current and baseline[p] != current[p])
    missing = sorted(p for p in baseline if p not in current)
    added = sorted(p for p in current if p not in baseline)
    gate["details"] = [{"modified": modified, "missing": missing, "added_not_in_baseline": added}]
    if modified or missing:
        return _finish(gate, "FAIL", f"modified={modified} missing={missing}")
    note = f" (new files not in baseline, review them: {added})" if added else ""
    return _finish(gate, "PASS", "all protected files match the baseline" + note)


# --------------------------------------------------------------------------- lint / sast
def gate_lint() -> dict:
    gate = _new_gate("lint", "NFR-001", "ruff exits 0 with zero violations on src/ and tests/.")
    if not (ROOT / "src").exists():
        return _finish(gate, "FAIL", "src/ directory does not exist")
    cmd = [sys.executable, "-m", "ruff", "check", "--config", ".harness/ruff.toml",
           "--output-format=concise", "src", "tests"]
    proc = _run(gate, cmd)
    if proc is None:
        return gate
    if proc.returncode == 0:
        return _finish(gate, "PASS", "ruff reported no violations")
    return _finish(gate, "FAIL", f"ruff exited {proc.returncode}; violations listed in output")


def gate_sast() -> dict:
    gate = _new_gate("sast", "NFR-002", "bandit exits 0: no MEDIUM or HIGH severity findings in src/.")
    if not (ROOT / "src").exists():
        return _finish(gate, "FAIL", "src/ directory does not exist")
    proc = _run(gate, [sys.executable, "-m", "bandit", "-r", "src", "-ll", "-f", "txt"])
    if proc is None:
        return gate
    if proc.returncode == 0:
        return _finish(gate, "PASS", "bandit reported no medium/high findings")
    return _finish(gate, "FAIL", f"bandit exited {proc.returncode}; findings listed in output")


# --------------------------------------------------------------------------- repo policy gates
def _iter_repo_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield Path(dirpath) / name


def gate_secrets() -> dict:
    gate = _new_gate("secrets", "NFR-006",
                     "No secret-looking strings and no .env / key files anywhere in the repo.")
    hits: list[str] = []
    for path in _iter_repo_files():
        rel = path.relative_to(ROOT).as_posix()
        name = path.name
        if name == ".env" or (name.startswith(".env.") and name != ".env.example") \
                or path.suffix in {".pem", ".key", ".p12"} or name in {"id_rsa", "id_ed25519"}:
            hits.append(f"{rel}: forbidden secret-bearing file name")
            continue
        if rel in SECRET_SELF_EXCLUDE or path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                hits.append(f"{rel}: matches {label}")
    gate["details"] = hits
    if hits:
        return _finish(gate, "FAIL", f"{len(hits)} finding(s): " + "; ".join(hits[:10]))
    return _finish(gate, "PASS", "no secrets or secret-bearing files found")


def gate_suppressions() -> dict:
    gate = _new_gate("suppressions", "NFR-007",
                     "src/ contains no noqa / nosec / type-ignore / lint-disable comments.")
    hits: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if SUPPRESSION_RE.search(line):
                hits.append(f"{path.relative_to(ROOT).as_posix()}:{lineno}: {line.strip()}")
    gate["details"] = hits
    if hits:
        return _finish(gate, "FAIL", f"{len(hits)} suppression comment(s): " + "; ".join(hits[:10]))
    return _finish(gate, "PASS", "no suppression comments in src/")


# --------------------------------------------------------------------------- tests
def _junit_failures(path: Path) -> list[dict]:
    if not path.exists():
        return []
    failures: list[dict] = []
    for case in ET.parse(path).getroot().iter("testcase"):
        for kind in ("failure", "error"):
            node = case.find(kind)
            if node is None:
                continue
            name = case.get("name", "")
            match = re.search(r"test_(ac|nfr)_(\d{3})", name)
            failures.append({
                "test": f"{case.get('classname', '')}::{name}",
                "requirement": f"{match.group(1).upper()}-{match.group(2)}" if match else None,
                "kind": kind,
                "message": (node.get("message") or "")[:500],
                "trace": (node.text or "")[:1500],
            })
    return failures


def gate_tests(run_id: str) -> dict:
    gate = _new_gate("tests", "AC-*, NFR-003",
                     "pytest exits 0: every AC test passes and line coverage of ratelimiter >= 90%.")
    junit = RESULTS / f"{run_id}-junit.xml"
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}",
           "--cov=ratelimiter", "--cov-report=term-missing", "--cov-fail-under=90"]
    proc = _run(gate, cmd)
    if proc is None:
        return gate
    failures = _junit_failures(junit)
    gate["details"] = failures
    if proc.returncode == 0:
        return _finish(gate, "PASS", "all tests passed and coverage threshold met")
    notes = []
    if failures:
        notes.append(f"{len(failures)} failing test(s): " + ", ".join(
            f["requirement"] or f["test"] for f in failures))
    if "Required test coverage" in (proc.stdout or ""):
        notes.append("coverage below the 90% threshold (NFR-003)")
    if proc.returncode == 5:
        notes.append("no tests were collected")
    return _finish(gate, "FAIL", f"pytest exited {proc.returncode}; " + ("; ".join(notes) or "see output"))


# --------------------------------------------------------------------------- traceability
def gate_traceability() -> dict:
    gate = _new_gate("traceability", "all",
                     "Every AC/NFR id in specs/*/spec.md has a test (or enforcing gate); no orphan tests.")
    specs = sorted(ROOT.glob("specs/*/spec.md"))
    if not specs:
        return _finish(gate, "FAIL", "no specs/*/spec.md found; run /speckit.specify first")
    spec_ids: set[str] = set()
    for spec in specs:
        spec_ids |= {f"{a}-{n}" for a, n in re.findall(r"\b(AC|NFR)-(\d{3})\b", spec.read_text("utf-8"))}
    tests_by_id: dict[str, list[str]] = {}
    for path in sorted((ROOT / "tests").rglob("*.py")):
        for match in re.finditer(r"^def (test_(ac|nfr)_(\d{3})\w*)", path.read_text("utf-8"), re.M):
            key = f"{match.group(2).upper()}-{match.group(3)}"
            tests_by_id.setdefault(key, []).append(match.group(1))
    missing = sorted(i for i in spec_ids if i not in tests_by_id and i not in GATE_COVERED)
    orphans = sorted(i for i in tests_by_id if i not in spec_ids)
    matrix = ["# Traceability matrix (generated by the harness)", "",
              "| Requirement | Enforced by |", "|---|---|"]
    for ident in sorted(spec_ids):
        enforced = ", ".join(tests_by_id.get(ident, [])) or (
            f"gate: {GATE_COVERED[ident]}" if ident in GATE_COVERED else "**NOTHING**")
        matrix.append(f"| {ident} | {enforced} |")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "traceability-latest.md").write_text("\n".join(matrix) + "\n", encoding="utf-8")
    gate["details"] = [{"spec_ids": len(spec_ids), "missing": missing, "orphans": orphans}]
    if missing or orphans:
        return _finish(gate, "FAIL", f"spec ids without tests: {missing}; tests without spec id: {orphans}")
    return _finish(gate, "PASS", f"all {len(spec_ids)} spec ids are enforced")


# --------------------------------------------------------------------------- reporting
def build_feedback(result: dict) -> str:
    lines = [
        "# Harness feedback for the coding agent", "",
        f"Run: {result['run_id']} | Overall: {result['overall']} | Commit: {result['git_commit']}", "",
        "## Repair rules (mandatory)",
        "- Fix the implementation under `src/` only.",
        "- Do NOT modify tests/, .harness/, pytest.ini, requirements-dev.txt or any Spec Kit artifact.",
        "- Do NOT add `# noqa`, `# nosec`, skips, xfails, or loosen any check.",
        "- If you believe the specification itself is wrong, STOP and report it; a human will amend",
        "  the spec upstream and record the change.",
        "- A human re-runs `python .harness/run_harness.py` after your change.", "",
    ]
    for gate in result["gates"]:
        if gate["status"] == "PASS":
            continue
        lines += [f"## Gate `{gate['name']}`: {gate['status']} (requirement {gate['requirement']})", "",
                  f"- Expected: {gate['expected']}", f"- Observed: {gate['observed']}"]
        if gate["command"]:
            lines.append(f"- Command: `{gate['command']}` (exit {gate['exit_code']})")
        lines.append("")
        if gate["name"] == "tests":
            for fail in gate["details"]:
                lines += [f"### Failing test `{fail['test']}` ({fail['requirement'] or 'no id'})",
                          f"- Assertion message (expected vs observed): {fail['message']}",
                          "```", fail["trace"], "```", ""]
        elif gate["details"]:
            lines += ["Details:", "```", json.dumps(gate["details"], indent=2)[:3000], "```", ""]
        if gate["output_tail"]:
            lines += ["Raw output (tail):", "```", gate["output_tail"], "```", ""]
    return "\n".join(lines) + "\n"


def run_all() -> int:
    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S")
    RESULTS.mkdir(parents=True, exist_ok=True)
    gates = [gate_integrity(), gate_lint(), gate_sast(), gate_secrets(), gate_suppressions(),
             gate_tests(run_id), gate_traceability()]
    overall = "PASS" if all(g["status"] == "PASS" for g in gates) else "FAIL"
    result = {"run_id": run_id, "timestamp_utc": _now(), "git_commit": _git_commit(),
              "python": sys.version.split()[0], "overall": overall, "gates": gates}
    (RESULTS / f"{run_id}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "latest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    with (RESULTS / "history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"run_id": run_id, "timestamp_utc": result["timestamp_utc"],
                             "git_commit": result["git_commit"], "overall": overall,
                             "gates": {g["name"]: g["status"] for g in gates}}) + "\n")
    if overall == "FAIL":
        feedback = build_feedback(result)
        (RESULTS / f"{run_id}-feedback.md").write_text(feedback, encoding="utf-8")
        (RESULTS / "feedback-latest.md").write_text(feedback, encoding="utf-8")
    print(f"\nHARNESS {run_id}")
    for g in gates:
        print(f"  [{g['status']:<5}] {g['name']:<13} {g['requirement']:<14} {g['observed'][:90]}")
    print(f"\nOVERALL: {overall}")
    if overall == "FAIL":
        print("Feedback for the coding agent: evidence/harness-results/feedback-latest.md")
    return 0 if overall == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Part 1A deterministic harness")
    parser.add_argument("--lock", action="store_true", help="HUMAN ONLY: re-baseline integrity hashes")
    args = parser.parse_args()
    return write_lock() if args.lock else run_all()


if __name__ == "__main__":
    sys.exit(main())
