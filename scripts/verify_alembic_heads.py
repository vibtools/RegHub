from __future__ import annotations

import subprocess
import sys


def parse_heads(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip().endswith("(head)")]


def main() -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode:
        raise RuntimeError(f"Alembic head inspection failed:\n{completed.stdout}")
    heads = parse_heads(completed.stdout)
    if len(heads) != 1:
        raise RuntimeError(f"Expected exactly one Alembic head, found {len(heads)}: {heads}")
    print(heads[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
