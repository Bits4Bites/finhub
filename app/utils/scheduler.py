"""Lightweight periodic background task scheduler."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PeriodicTask:
    """Definition of a periodic background task."""

    name: str
    func: Callable[[], Coroutine[Any, Any, None]]
    interval_seconds: float
    run_on_start: bool = True


@dataclass
class BackgroundScheduler:
    """Manages periodic background tasks.

    Usage:
        scheduler = BackgroundScheduler()
        scheduler.register(PeriodicTask(name="refresh_cache", func=my_func, interval_seconds=3600))

        # In main/bootstrapper script:
        await scheduler.start()
        yield
        await scheduler.stop()
    """

    _tasks: list[PeriodicTask] = field(default_factory=list)
    _running: list[asyncio.Task] = field(default_factory=list)

    def register(self, task: PeriodicTask) -> None:
        """Register a periodic task to be started later."""
        logger.info("Registering periodic task '%s' to run every %ds", task.name, task.interval_seconds)
        self._tasks.append(task)

    async def start(self) -> None:
        """Start all registered periodic tasks."""
        for task in self._tasks:
            asyncio_task = asyncio.create_task(self._run_loop(task), name=f"periodic:{task.name}")
            self._running.append(asyncio_task)
            logger.info("Scheduled periodic task '%s' every %ds", task.name, task.interval_seconds)

    async def stop(self) -> None:
        """Cancel all running periodic tasks and wait for them to finish."""
        for task in self._running:
            task.cancel()
        await asyncio.gather(*self._running, return_exceptions=True)
        self._running.clear()
        logger.info("All periodic tasks stopped")

    async def _run_loop(self, task: PeriodicTask) -> None:
        """Execute a task periodically until canceled."""
        if task.run_on_start:
            await self._execute(task)

        while True:
            try:
                await asyncio.sleep(task.interval_seconds)
                await self._execute(task)
            except asyncio.CancelledError:
                break

    @staticmethod
    async def _execute(task: PeriodicTask) -> None:
        """Execute a single task with error handling."""
        try:
            await task.func()
        except Exception as exc:
            logger.error("Periodic task '%s' failed: %s", task.name, exc)
