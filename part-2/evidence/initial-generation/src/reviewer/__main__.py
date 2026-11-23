"""Command-line interface: ``python -m reviewer review PATH [--diff]`` (contracts/cli.md).

Exit codes: 0 result printed; 1 other ReviewerError; 2 usage, unreadable file, invalid input
or missing configuration; 3 LLMServiceError; 4 ModelOutputError. Errors go to stderr and
never include credentials.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from reviewer.errors import ConfigurationError, LLMServiceError, ModelOutputError, ReviewerError
from reviewer.service import review_code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m reviewer", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    review = commands.add_parser("review", help="review a Python file or a unified diff")
    review.add_argument("path", type=Path, help="file to review (UTF-8)")
    review.add_argument("--diff", action="store_true", help="treat the file as a unified diff")
    return parser


def _fail(message: str, code: int) -> int:
    print(f"error: {message}", file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        code = args.path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return _fail(f"cannot read {args.path}: {exc}", 2)
    try:
        result = review_code(code, kind="diff" if args.diff else "snippet")
    except ValueError as exc:
        return _fail(str(exc), 2)
    except ConfigurationError as exc:
        return _fail(str(exc), 2)
    except LLMServiceError as exc:
        return _fail(f"model service error: {exc}", 3)
    except ModelOutputError as exc:
        return _fail(f"model output error: {exc}", 4)
    except ReviewerError as exc:
        return _fail(str(exc), 1)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
