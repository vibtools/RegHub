from __future__ import annotations

import argparse
import subprocess
import sys
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a command with bounded retry. The wrapper never edits source files; "
            "it only re-executes the supplied process."
        )
    )
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--initial-delay", type=float, default=3.0)
    parser.add_argument("--max-delay", type=float, default=15.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    args.attempts = max(1, min(args.attempts, 5))
    args.initial_delay = max(0.0, args.initial_delay)
    args.max_delay = max(args.initial_delay, args.max_delay)
    return args


def main() -> int:
    args = parse_args()
    delay = args.initial_delay
    for attempt in range(1, args.attempts + 1):
        print(f"[retry] attempt {attempt}/{args.attempts}: {' '.join(args.command)}", flush=True)
        try:
            completed = subprocess.run(args.command, check=False)  # noqa: S603
            return_code = int(completed.returncode)
        except OSError as exc:
            return_code = 127
            print(f"[retry] process start failed: {exc}", file=sys.stderr, flush=True)
        if return_code == 0:
            return 0
        if attempt >= args.attempts:
            print(f"[retry] command failed after {attempt} attempt(s)", file=sys.stderr)
            return return_code
        print(f"[retry] exit code {return_code}; retrying in {delay:.1f}s", file=sys.stderr)
        time.sleep(delay)
        delay = min(args.max_delay, max(1.0, delay * 2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
