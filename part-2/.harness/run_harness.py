#!/usr/bin/env python3
"""Single harness runner for Part 1B (Semantic Code Review & Refactoring Assistant).

Pipeline (one command):
    preflight gates -> evaluation dataset -> application/model call -> Layer 1 schema
    -> Layer 2 invariants/properties -> Layer 3 semantic/quality -> aggregate vs the
    threshold declared in the spec -> PASS / FAIL / INCONCLUSIVE -> structured feedback.

Usage:
    python .harness/run_harness.py                  full run (needs API credentials)
    python .harness/run_harness.py --skip-eval      preflight gates only (no API calls)
    python .harness/run_harness.py --cases N01,G02  debug subset (not official evidence)
    python .harness/run_harness.py --repeats 3      run every case 3 times
    python .harness/run_harness.py --stub ideal     self-test the harness offline (not evidence)
    python .harness/run_harness.py --lock           (HUMAN ONLY) re-baseline integrity hashes

Exit codes: 0 PASS, 1 FAIL, 2 INCONCLUSIVE (service problems / not configured).
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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / ".harness"
RESULTS = ROOT / "evidence" / "harness-results"
LOCK_FILE = HARNESS / "integrity.lock.json"
DATASET = ROOT / "evals" / "dataset.json"
CONFIG = HARNESS / "eval_config.json"
TAIL_CHARS = 5000
sys.path[:0] = [str(HARNESS), str(ROOT / "src")]

PROTECTED_GLOBS = [
    "tests/**/*.py", "evals/dataset.json", ".harness/*.py", ".harness/evaluators/*.py",
    ".harness/eval_config.json", ".harness/ruff.toml", "pytest.ini", "requirements-dev.txt",
]
# Spec ids enforced by runner logic rather than by a dataset case or evaluator check.
GATE_COVERED = {
    "EVAL-001": "decision: aggregate_score", "EVAL-002": "decision: issue_recall",
    "EVAL-003": "decision: schema_validity_rate", "EVAL-004": "decision: guardrail_pass_rate",
    "EVAL-005": "service errors separated; > max rate -> INCONCLUSIVE",
    "NFR-001": "lint", "NFR-002": "secrets", "NFR-003": "integrity",
    "NFR-004": "model configuration recorded and temperature checked",
}
ID_RE = r"\b(?:FR|SCH|INV|BEH|GR|EVAL|NFR)-\d{3}\b"
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".ruff_cache",
             ".pytest_cache", "harness-results", "htmlcov", "initial-generation", "final-generation"}
# Test fixtures intentionally contain FAKE secret-shaped strings to exercise redaction.
SECRET_SCAN_EXCLUDE = ("evals/dataset.json", "tests/", ".harness/", "speckit-prompts/")
SECRET_PATTERNS = [
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("api-key-like", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}")),
    ("hardcoded-credential", re.compile(
        r"(?i)\b(?:api[_-]?key|secret|passwd|password|token)\b\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']")),
]


# --------------------------------------------------------------------------- helpers
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha(path.read_bytes())


def _tail(text: str) -> str:
    return text if len(text) <= TAIL_CHARS else "...[truncated]...\n" + text[-TAIL_CHARS:]


def _git_commit() -> str | None:
    try:
        proc = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=False, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() or None if proc.returncode == 0 else None


def _gate(name: str, requirement: str, expected: str) -> dict:
    return {"name": name, "requirement": requirement, "status": "FAIL", "expected": expected,
            "observed": "", "command": None, "exit_code": None, "duration_s": 0.0,
            "output_tail": "", "details": []}


def _done(gate: dict, status: str, observed: str) -> dict:
    gate["status"], gate["observed"] = status, observed
    return gate


def _run(gate: dict, cmd: list[str]):
    gate["command"] = " ".join(cmd)
    started = time.perf_counter()
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", check=False, timeout=900)
    except (OSError, subprocess.SubprocessError) as exc:
        gate["duration_s"] = round(time.perf_counter() - started, 2)
        _done(gate, "ERROR", f"could not execute command: {exc}")
        return None
    gate["duration_s"] = round(time.perf_counter() - started, 2)
    gate["exit_code"] = proc.returncode
    gate["output_tail"] = _tail((proc.stdout or "") + ("\n[stderr]\n" + proc.stderr if proc.stderr else ""))
    if proc.returncode != 0 and "No module named" in (proc.stderr or ""):
        _done(gate, "ERROR", "tool or dependency not installed (environment problem, not an "
              "application failure): run `pip install -r requirements-dev.txt`")
        return None
    return proc


def _load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _spec_text() -> str:
    return "\n".join(p.read_text("utf-8") for p in sorted(ROOT.glob("specs/*/spec.md")))


# --------------------------------------------------------------------------- integrity
def _protected_files() -> dict[str, str]:
    files: dict[str, str] = {}
    for pattern in PROTECTED_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path.is_file() and "__pycache__" not in path.parts:
                files[path.relative_to(ROOT).as_posix()] = _sha_file(path)
    return files


def write_lock() -> int:
    files = _protected_files()
    LOCK_FILE.write_text(json.dumps({"created_utc": _now(), "files": files}, indent=2) + "\n", "utf-8")
    RESULTS.mkdir(parents=True, exist_ok=True)
    with (RESULTS / "baseline-changes.log").open("a", encoding="utf-8") as fh:
        fh.write(f"{_now()} baseline lock written: {len(files)} protected files, "
                 f"lock sha256={_sha_file(LOCK_FILE)[:12]}, commit={_git_commit()}\n")
    print(f"Baseline written for {len(files)} protected files. Review the git diff and log WHY.")
    return 0


def gate_integrity() -> dict:
    gate = _gate("integrity", "NFR-003",
                 "Dataset, evaluators, thresholds, tests and harness match the human-approved baseline.")
    if not LOCK_FILE.exists():
        return _done(gate, "FAIL", "no baseline lock. A human must run: python .harness/run_harness.py --lock")
    baseline = json.loads(LOCK_FILE.read_text("utf-8"))["files"]
    current = _protected_files()
    modified = sorted(p for p in baseline if p in current and baseline[p] != current[p])
    missing = sorted(p for p in baseline if p not in current)
    added = sorted(p for p in current if p not in baseline)
    gate["details"] = [{"modified": modified, "missing": missing, "added_not_in_baseline": added}]
    if modified or missing:
        return _done(gate, "FAIL", f"modified={modified} missing={missing}")
    return _done(gate, "PASS", "all protected files match the baseline"
                 + (f" (new unlocked files: {added})" if added else ""))


# --------------------------------------------------------------------------- spec-level gates
def gate_dataset() -> dict:
    gate = _gate("dataset", "FR-002",
                 "evals/dataset.json has >= 15 well-formed cases covering all categories, each with an oracle.")
    from evaluators import CATEGORIES, STATUSES, split_lines
    cfg = _load_config()
    problems: list[str] = []
    try:
        cases = json.loads(DATASET.read_text("utf-8"))["cases"]
    except (OSError, ValueError, KeyError) as exc:
        return _done(gate, "FAIL", f"dataset unreadable: {exc}")
    spec_ids = set(re.findall(ID_RE, _spec_text()))
    if len(cases) < cfg["dataset_min_cases"]:
        problems.append(f"only {len(cases)} cases (< {cfg['dataset_min_cases']})")
    ids = [c.get("id") for c in cases]
    if len(ids) != len(set(ids)):
        problems.append("duplicate case ids")
    missing_cats = sorted(set(cfg["required_categories"]) - {c.get("category") for c in cases})
    if missing_cats:
        problems.append(f"missing categories {missing_cats}")
    if sum(1 for c in cases if "guardrail" in c.get("tags", [])) < 3:
        problems.append("fewer than 3 guardrail-tagged cases")
    for case in cases:
        cid = case.get("id", "?")
        for key in ("id", "category", "requirements", "kind", "language", "input", "expected"):
            if key not in case:
                problems.append(f"{cid}: missing key {key}")
        exp = case.get("expected", {})
        if not set(exp.get("status_any", [])) <= set(STATUSES) or not exp.get("status_any"):
            problems.append(f"{cid}: invalid expected.status_any")
        if case.get("kind") not in ("snippet", "diff"):
            problems.append(f"{cid}: invalid kind")
        if spec_ids:
            unknown = [r for r in case.get("requirements", []) if r not in spec_ids]
            if unknown:
                problems.append(f"{cid}: requirement ids not in spec: {unknown}")
        lines = split_lines(case.get("input", ""))
        for issue in exp.get("issues", []):
            low, high = issue["lines"]
            window = "\n".join(lines[low - 1:high])
            if not 1 <= low <= high <= max(len(lines), 1) or issue.get("anchor", "") not in window:
                problems.append(f"{cid}/{issue['id']}: labelled lines {low}-{high} do not contain the anchor")
            if not set(issue["categories_any"]) <= set(CATEGORIES):
                problems.append(f"{cid}/{issue['id']}: unknown category")
        if not exp.get("issues") and not any(k in exp for k in ("max_findings", "max_severity", "llm_calls")):
            problems.append(f"{cid}: no oracle (issues, max_findings, max_severity or llm_calls)")
    gate["details"] = problems
    if not spec_ids:
        problems.append("no specs/*/spec.md found, requirement ids could not be verified")
    if problems:
        return _done(gate, "FAIL", f"{len(problems)} problem(s): " + "; ".join(problems[:6]))
    return _done(gate, "PASS", f"{len(cases)} cases, all categories covered, ground truth consistent")


def gate_threshold_declared() -> dict:
    gate = _gate("threshold-declared", "EVAL-001..004",
                 "The spec declares the same thresholds that the harness enforces (declared BEFORE evaluation).")
    spec = _spec_text()
    if not spec:
        return _done(gate, "FAIL", "no specs/*/spec.md found")
    bad = []
    for metric, value in _load_config()["thresholds"].items():
        match = re.search(rf"\b{metric}\b[`*\s]*(?:>=|≥|==|=)[`*\s]*([0-9]*\.?[0-9]+)", spec)
        if not match:
            bad.append(f"{metric}: not declared in spec")
        elif abs(float(match.group(1)) - float(value)) > 1e-9:
            bad.append(f"{metric}: spec says {match.group(1)}, harness enforces {value}")
    gate["details"] = bad
    return _done(gate, "FAIL" if bad else "PASS", "; ".join(bad) if bad else "spec thresholds match eval_config.json")


def gate_traceability() -> dict:
    gate = _gate("traceability", "all", "Every spec requirement id is referenced by a test, dataset case, "
                 "evaluator check or enforcing gate; no dataset/test id is missing from the spec.")
    spec_ids = set(re.findall(ID_RE, _spec_text()))
    if not spec_ids:
        return _done(gate, "FAIL", "no specs/*/spec.md with requirement ids found")
    covered: dict[str, list[str]] = {}

    def add(ident: str, where: str) -> None:
        covered.setdefault(ident, []).append(where)

    for path in sorted((ROOT / "tests").glob("*.py")):
        for m in re.finditer(r"^def (test_(fr|sch|inv|beh|gr|eval|nfr)_(\d{3})\w*)", path.read_text("utf-8"), re.M):
            add(f"{m.group(2).upper()}-{m.group(3)}", f"test {m.group(1)}")
    for path in sorted((HARNESS / "evaluators").glob("*.py")):
        for ident in set(re.findall(ID_RE, path.read_text("utf-8"))):
            add(ident, f"evaluator {path.stem}")
    try:
        for case in json.loads(DATASET.read_text("utf-8"))["cases"]:
            for ident in case.get("requirements", []):
                add(ident, f"case {case['id']}")
    except (OSError, ValueError, KeyError):
        pass
    for ident, why in GATE_COVERED.items():
        add(ident, f"gate: {why}")
    missing = sorted(i for i in spec_ids if i not in covered)
    orphans = sorted(i for i in covered if i not in spec_ids and not i.startswith(("SCH-",)))
    matrix = ["# Traceability matrix (generated by the harness)", "", "| Requirement | Enforced by |", "|---|---|"]
    for ident in sorted(spec_ids):
        where = covered.get(ident, ["**NOTHING**"])
        matrix.append(f"| {ident} | {'; '.join(where[:4])}{' ...' if len(where) > 4 else ''} |")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "traceability-latest.md").write_text("\n".join(matrix) + "\n", encoding="utf-8")
    gate["details"] = [{"spec_ids": len(spec_ids), "uncovered": missing, "ids_not_in_spec": orphans}]
    if missing or orphans:
        return _done(gate, "FAIL", f"spec ids with no check: {missing}; ids used but not in spec: {orphans}")
    return _done(gate, "PASS", f"all {len(spec_ids)} spec ids are covered")


def gate_secrets() -> dict:
    gate = _gate("secrets", "NFR-002", "No API keys, tokens, .env files or key files in the repository.")
    hits: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            rel = path.relative_to(ROOT).as_posix()
            if name == ".env" or (name.startswith(".env.") and name != ".env.example") \
                    or path.suffix in {".pem", ".key", ".p12"}:
                hits.append(f"{rel}: forbidden secret-bearing file name")
                continue
            if rel.startswith(SECRET_SCAN_EXCLUDE) or path.stat().st_size > 1_000_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            hits += [f"{rel}: matches {label}" for label, pat in SECRET_PATTERNS if pat.search(text)]
    gate["details"] = hits
    if hits:
        return _done(gate, "FAIL", f"{len(hits)} finding(s): " + "; ".join(hits[:8]))
    return _done(gate, "PASS", "no secrets or secret-bearing files found")


def gate_lint() -> dict:
    gate = _gate("lint", "NFR-001", "ruff exits 0 with zero violations on src/ and tests/.")
    if not (ROOT / "src").exists():
        return _done(gate, "FAIL", "src/ directory does not exist")
    proc = _run(gate, [sys.executable, "-m", "ruff", "check", "--config", ".harness/ruff.toml",
                       "--output-format=concise", "src", "tests"])
    if proc is None:
        return gate
    return _done(gate, "PASS" if proc.returncode == 0 else "FAIL",
                 "ruff reported no violations" if proc.returncode == 0 else f"ruff exited {proc.returncode}")


def _junit_failures(path: Path) -> list[dict]:
    import xml.etree.ElementTree as ET
    if not path.exists():
        return []
    out = []
    for case in ET.parse(path).getroot().iter("testcase"):
        for kind in ("failure", "error"):
            node = case.find(kind)
            if node is not None:
                out.append({"test": f"{case.get('classname', '')}::{case.get('name', '')}", "kind": kind,
                            "message": (node.get("message") or "")[:500], "trace": (node.text or "")[:1500]})
    return out


def gate_tests(run_id: str) -> dict:
    gate = _gate("unit-tests", "FR-001..006, INV-*, GR-*",
                 "pytest exits 0: deterministic application contract tests and evaluator self-tests pass.")
    junit = RESULTS / f"{run_id}-junit.xml"
    proc = _run(gate, [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"])
    if proc is None:
        return gate
    gate["details"] = _junit_failures(junit)
    if proc.returncode == 0:
        return _done(gate, "PASS", "all unit tests passed")
    return _done(gate, "FAIL", f"pytest exited {proc.returncode}; {len(gate['details'])} failing test(s)")


# --------------------------------------------------------------------------- evaluation
class RecordingClient:
    """Counts model calls so properties like 'no model call for empty input' are checkable."""

    def __init__(self, inner) -> None:
        self.inner, self.calls = inner, 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return self.inner.complete(system, user)

    def describe(self) -> dict:
        return self.inner.describe()


def _score(checks: list, weights: dict) -> tuple[float, dict]:
    layers: dict[str, list[bool]] = {}
    for c in checks:
        layers.setdefault(c.layer, []).append(c.passed)
    layer_scores = {k: round(sum(v) / len(v), 4) for k, v in layers.items()}
    if any(not c.passed for c in checks if c.layer == "structural"):
        return 0.0, layer_scores
    total = sum(weights[k] for k in layers)
    return round(sum(weights[k] * layer_scores[k] for k in layers) / total, 4), layer_scores


def _evaluate_sample(case: dict, client, cfg: dict, review_code, errors, stub) -> dict:
    from evaluators import match_issues, property_checks, semantic_checks, structural_checks
    svc = cfg["service"]
    output = raised = None
    recording = None
    for attempt in range(1, svc["max_attempts"] + 1):
        recording = RecordingClient(client)
        if stub is not None:
            stub.current_case = case
        started = time.perf_counter()
        try:
            output = review_code(case["input"], kind=case["kind"], language=case["language"], client=recording)
            raised = None
        except errors.LLMServiceError as exc:
            if attempt < svc["max_attempts"]:
                time.sleep(0 if stub is not None else svc["backoff_seconds"] * attempt)
                continue
            return {"case_id": case["id"], "status": "SERVICE_ERROR", "attempts": attempt,
                    "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
        except errors.ModelOutputError as exc:
            output, raised = None, f"ModelOutputError: {str(exc)[:300]}"
        except Exception as exc:  # application defect: reported as a structural failure
            output, raised = None, f"unexpected {type(exc).__name__}: {str(exc)[:300]}"
        break
    latency = round(time.perf_counter() - started, 3)
    checks = structural_checks(output, raised)
    matches: list[dict] = []
    if all(c.passed for c in checks):
        checks += property_checks(case, output, recording.calls)
        checks += semantic_checks(case, output)
        matches = match_issues(case, output)
    score, layer_scores = _score(checks, cfg["weights"])
    failed = [c.to_dict() for c in checks if not c.passed]
    structural_ok = all(c.passed for c in checks if c.layer == "structural")
    guardrail_ok = all(c.passed for c in checks if c.layer in ("structural", "property")
                       or c.name == "issue_detected")
    return {"case_id": case["id"], "category": case["category"], "tags": case.get("tags", []),
            "status": "PASS" if not failed else "FAIL", "score": score, "layer_scores": layer_scores,
            "structural_ok": structural_ok, "guardrail_ok": guardrail_ok, "llm_calls": recording.calls,
            "latency_s": latency, "matches": matches, "failed_checks": failed,
            "checks_total": len(checks), "output": output, "raised": raised}


def _prompt_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted((ROOT / "prompts").rglob("*")) if (ROOT / "prompts").exists() else []:
        if path.is_file():
            digest.update(path.relative_to(ROOT).as_posix().encode() + path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()[:16]


def run_evaluation(args, run_id: str) -> dict:
    cfg = _load_config()
    cases = json.loads(DATASET.read_text("utf-8"))["cases"]
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    result: dict = {"run_id": run_id, "timestamp_utc": _now(), "git_commit": _git_commit(),
                    "python": sys.version.split()[0], "mode": "stub" if args.stub else "live",
                    "partial": bool(args.cases), "repeats": args.repeats, "thresholds": cfg["thresholds"],
                    "weights": cfg["weights"], "dataset_sha256": _sha_file(DATASET)[:16],
                    "eval_config_sha256": _sha_file(CONFIG)[:16], "prompt_sha256": _prompt_hash()}
    stub = None
    try:
        import reviewer.errors as errors
        from reviewer.service import review_code
        if args.stub:
            from stub_client import StubClient
            stub = StubClient(args.stub)
            client = stub
        else:
            from reviewer.llm import build_client_from_env
            client = build_client_from_env()
    except ModuleNotFoundError as exc:
        return {**result, "decision": "FAIL", "reason": f"application not importable: {exc}", "samples": []}
    except Exception as exc:
        if type(exc).__name__ == "ConfigurationError":
            return {**result, "decision": "INCONCLUSIVE", "samples": [],
                    "reason": f"model client not configured (set credentials via environment variables): {exc}"}
        return {**result, "decision": "FAIL", "reason": f"could not build model client: {exc!r}", "samples": []}

    described = dict(client.describe())
    result["model_config"] = {k: described.get(k) for k in ("provider", "model", "temperature", "max_tokens")}
    problems = []
    temp = described.get("temperature")
    if not described.get("model") or not described.get("provider"):
        problems.append("client.describe() must report provider and model (NFR-004)")
    if not isinstance(temp, (int, float)) or temp > cfg["temperature_max"]:
        problems.append(f"temperature {temp!r} violates NFR-004 (must be <= {cfg['temperature_max']})")
    result["config_problems"] = problems

    samples = []
    for case in cases:
        for run in range(1, args.repeats + 1):
            sample = _evaluate_sample(case, client, cfg, review_code, errors, stub)
            sample["run"] = run
            samples.append(sample)
            print(f"  {case['id']:<4} run {run}: {sample['status']:<13} "
                  f"{('score ' + str(sample['score'])) if 'score' in sample else sample.get('error', '')}")
    result["samples"] = samples
    scored = [s for s in samples if s["status"] != "SERVICE_ERROR"]
    service_rate = (len(samples) - len(scored)) / len(samples) if samples else 0.0
    expected_total = detected = 0
    for sample in scored:
        for match in sample["matches"]:
            expected_total += 1
            detected += match["finding_index"] is not None
    # a missed issue in a structurally invalid sample still counts against recall
    case_by_id = {c["id"]: c for c in cases}
    for sample in scored:
        if not sample["matches"]:
            expected_total += len(case_by_id[sample["case_id"]]["expected"].get("issues", []))
    guard = [s for s in scored if "guardrail" in s["tags"]]
    clean = [s for s in scored if case_by_id[s["case_id"]]["category"] in ("boundary", "ambiguous")
             and not case_by_id[s["case_id"]]["expected"].get("issues")]
    result["metrics"] = {
        "aggregate_score": round(sum(s["score"] for s in scored) / len(scored), 4) if scored else None,
        "issue_recall": round(detected / expected_total, 4) if expected_total else None,
        "schema_validity_rate": round(sum(s["structural_ok"] for s in scored) / len(scored), 4) if scored else None,
        "guardrail_pass_rate": round(sum(s["guardrail_ok"] for s in guard) / len(guard), 4) if guard else None,
        "clean_case_false_positive_rate": round(sum(1 for s in clean if s["status"] == "FAIL") / len(clean), 4) if clean else None,
        "service_error_rate": round(service_rate, 4), "samples": len(samples), "scored_samples": len(scored),
        "issues_detected": f"{detected}/{expected_total}",
    }
    met = {k: (result["metrics"][k] is not None and result["metrics"][k] >= v - 1e-9)
           for k, v in cfg["thresholds"].items()}
    result["thresholds_met"] = met
    if not scored or service_rate > svc_max(cfg):
        result["decision"], result["reason"] = "INCONCLUSIVE", (
            f"service error rate {service_rate:.0%} exceeds {svc_max(cfg):.0%}; rerun when the provider is healthy")
    elif problems or not all(met.values()):
        result["decision"] = "FAIL"
        result["reason"] = "; ".join(problems + [f"{k} below threshold" for k, ok in met.items() if not ok])
    else:
        result["decision"], result["reason"] = "PASS", "all thresholds met; human review required next"
    return result


def svc_max(cfg: dict) -> float:
    return cfg["service"]["max_service_error_rate"]


# --------------------------------------------------------------------------- reporting
def build_feedback(preflight: list[dict], evaluation: dict | None) -> str:
    lines = ["# Harness feedback for the coding agent", "",
             "## Repair rules (mandatory)",
             "- You MAY change: `src/` (application code, parsers, validators, guardrails) and `prompts/`.",
             "- You MUST NOT change: `tests/`, `evals/dataset.json`, `.harness/`, thresholds, `pytest.ini`,",
             "  `requirements-dev.txt`, or any Spec Kit artifact. Do not delete or skip cases, do not lower",
             "  the declared thresholds, do not disable guardrails, do not special-case dataset inputs.",
             "- Fix the ROOT CAUSE in general terms (a prompt rule, a parser, a validator), not by matching",
             "  the literal text of an evaluation case.",
             "- If you believe the specification is wrong, STOP and report it; a human amends the spec.", ""]
    for gate in preflight:
        if gate["status"] == "PASS":
            continue
        lines += [f"## Preflight gate `{gate['name']}`: {gate['status']} ({gate['requirement']})",
                  f"- Expected: {gate['expected']}", f"- Observed: {gate['observed']}"]
        for fail in gate["details"] if gate["name"] == "unit-tests" else []:
            lines += [f"### Failing test `{fail['test']}`", "```", fail["message"], fail["trace"], "```"]
        if gate["name"] != "unit-tests" and gate["details"]:
            lines += ["```", json.dumps(gate["details"], indent=2)[:2500], "```"]
        if gate["output_tail"]:
            lines += ["Raw output (tail):", "```", gate["output_tail"], "```"]
        lines.append("")
    if evaluation and evaluation.get("samples"):
        lines += ["## Evaluation result", f"- Decision: **{evaluation['decision']}** ({evaluation['reason']})",
                  f"- Metrics: {json.dumps(evaluation.get('metrics', {}))}",
                  f"- Thresholds: {json.dumps(evaluation['thresholds'])}", ""]
        for s in evaluation["samples"]:
            if s["status"] != "FAIL":
                continue
            lines += [f"### Case {s['case_id']} ({s['category']}, run {s['run']}), score {s['score']}",
                      f"Output (truncated): `{json.dumps(s['output'])[:1200] if s['output'] is not None else s['raised']}`"]
            for c in s["failed_checks"]:
                lines.append(f"- FAILED [{c['layer']}] {c['name']} (requirement {c['requirement']}): "
                             f"expected {c['expected']} | observed {c['observed']}")
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Part 1B single harness")
    parser.add_argument("--lock", action="store_true", help="HUMAN ONLY: re-baseline integrity hashes")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--force-eval", action="store_true", help="run evaluation even if preflight fails (not evidence)")
    parser.add_argument("--stub", choices=["ideal", "sloppy"], help="offline harness self-test (not evidence)")
    parser.add_argument("--cases", help="comma-separated case ids (debug subset, not official evidence)")
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    if args.lock:
        return write_lock()

    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S")
    RESULTS.mkdir(parents=True, exist_ok=True)
    preflight = [gate_integrity(), gate_dataset(), gate_threshold_declared(), gate_traceability(),
                 gate_secrets(), gate_lint(), gate_tests(run_id)]
    pre_ok = all(g["status"] == "PASS" for g in preflight)
    print(f"\nHARNESS {run_id}\nPreflight gates:")
    for g in preflight:
        print(f"  [{g['status']:<5}] {g['name']:<18} {g['requirement']:<14} {g['observed'][:80]}")

    evaluation = None
    official = pre_ok and not args.stub and not args.cases
    if args.skip_eval:
        print("\nEvaluation skipped (--skip-eval).")
    elif pre_ok or args.force_eval or args.stub:
        print(f"\nEvaluation ({'stub: NOT evidence' if args.stub else 'live'}):")
        evaluation = run_evaluation(args, run_id)
        evaluation["preflight_passed"] = pre_ok
        name = "eval" if official else "eval-debug"
        (RESULTS / f"{run_id}-{name}.json").write_text(json.dumps(evaluation, indent=2) + "\n", "utf-8")
        if official:
            (ROOT / "evidence" / "eval-results.json").write_text(json.dumps(evaluation, indent=2) + "\n", "utf-8")
        print(f"\nMetrics : {json.dumps(evaluation.get('metrics', {}))}")
        print(f"Decision: {evaluation['decision']}  ({evaluation['reason']})"
              + ("" if official else "   [not official evidence]"))
    else:
        print("\nEvaluation NOT run because preflight gates did not all pass (fix them first).")

    decision = evaluation["decision"] if evaluation else ("FAIL" if not pre_ok else "NOT_RUN")
    overall = "FAIL" if not pre_ok and not args.skip_eval else decision
    if args.skip_eval:
        overall = "PREFLIGHT_PASS" if pre_ok else "FAIL"
    history = {"run_id": run_id, "timestamp_utc": _now(), "git_commit": _git_commit(), "overall": overall,
               "preflight": {g["name"]: g["status"] for g in preflight},
               "mode": "stub" if args.stub else "live", "official": official,
               "metrics": (evaluation or {}).get("metrics")}
    with (RESULTS / "history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(history) + "\n")
    (RESULTS / f"{run_id}-preflight.json").write_text(json.dumps(preflight, indent=2) + "\n", "utf-8")
    if overall == "FAIL" or (evaluation and evaluation["decision"] == "FAIL"):
        feedback = build_feedback(preflight, evaluation)
        (RESULTS / f"{run_id}-feedback.md").write_text(feedback, "utf-8")
        (RESULTS / "feedback-latest.md").write_text(feedback, "utf-8")
        print("Feedback for the coding agent: evidence/harness-results/feedback-latest.md")
    print(f"\nOVERALL: {overall}")
    return {"PASS": 0, "PREFLIGHT_PASS": 0, "FAIL": 1}.get(overall, 2)


if __name__ == "__main__":
    sys.exit(main())
