import asyncio
import signal

from app.container import ApplicationContainer
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.engine import engine


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.operation_backend != "redis":
        raise RuntimeError("Set OPERATION_BACKEND=redis before starting the RegHub worker")
    container = ApplicationContainer(settings)
    await container.initialize(worker_process=True)
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signal_name, stop.set)
    worker_task = asyncio.create_task(container.operation_runner.run_forever())
    await stop.wait()
    worker_task.cancel()
    await asyncio.gather(worker_task, return_exceptions=True)
    await container.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
