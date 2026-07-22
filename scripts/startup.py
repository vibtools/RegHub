from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time

import asyncpg

_STARTUP_LOCK_ID = 904_797_523_282_58
_DEFAULT_DATABASE_URL = "postgresql+asyncpg://reghub:reghub@localhost:5432/reghub"
_LOCK_TIMEOUT_SECONDS = 300.0
_LOCK_POLL_SECONDS = 1.0
_COMMAND_TIMEOUT_SECONDS = 900


def normalize_database_dsn(value: str) -> str:
    candidate = value.strip()
    if candidate.startswith("postgresql+asyncpg://"):
        return "postgresql://" + candidate.removeprefix("postgresql+asyncpg://")
    if candidate.startswith("postgres://"):
        return "postgresql://" + candidate.removeprefix("postgres://")
    if candidate.startswith("postgresql://"):
        return candidate
    raise ValueError("DATABASE_URL must use PostgreSQL for container startup")


def run_startup_command(*args: str) -> None:
    # The argument vector is assembled only from fixed internal module commands.
    subprocess.run(args, check=True, timeout=_COMMAND_TIMEOUT_SECONDS)  # noqa: S603


async def acquire_lock(connection: asyncpg.Connection) -> None:
    deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
    while True:
        acquired = await connection.fetchval(
            "SELECT pg_try_advisory_lock($1)",
            _STARTUP_LOCK_ID,
        )
        if acquired:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out waiting for the RegHub startup migration lock")
        await asyncio.sleep(_LOCK_POLL_SECONDS)


async def run_startup() -> None:
    dsn = normalize_database_dsn(os.getenv("DATABASE_URL", _DEFAULT_DATABASE_URL))
    connection = await asyncpg.connect(dsn, timeout=20)
    locked = False
    try:
        await acquire_lock(connection)
        locked = True
        run_startup_command(sys.executable, "-m", "alembic", "upgrade", "head")
        run_startup_command(sys.executable, "-m", "scripts.seed")
    finally:
        try:
            if locked:
                await connection.execute("SELECT pg_advisory_unlock($1)", _STARTUP_LOCK_ID)
        finally:
            await connection.close()


def main() -> int:
    asyncio.run(run_startup())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
