"""Container simulation — the smallest runnable unit inside a Pod."""

from __future__ import annotations

import random
import time
import uuid
from enum import Enum


class ContainerStatus(str, Enum):
    CREATED = "Created"
    RUNNING = "Running"
    TERMINATED = "Terminated"
    FAILED = "Failed"
    RESTARTING = "Restarting"


class Container:
    """Simulates a single container with its own lifecycle and resource usage."""

    def __init__(
        self,
        name: str,
        image: str,
        cpu_request: int = 100,
        memory_request: int = 128,
        failure_rate: float = 0.05,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.image = image
        self.cpu_request = cpu_request
        self.memory_request = memory_request
        self.failure_rate = failure_rate

        self.status = ContainerStatus.CREATED
        self.restart_count = 0
        self.created_at = time.time()
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.exit_code: int | None = None

    def start(self) -> bool:
        if self.status in (ContainerStatus.CREATED, ContainerStatus.RESTARTING):
            self.status = ContainerStatus.RUNNING
            self.started_at = time.time()
            return True
        return False

    def stop(self, exit_code: int = 0) -> None:
        self.status = ContainerStatus.TERMINATED
        self.finished_at = time.time()
        self.exit_code = exit_code

    def fail(self) -> None:
        self.status = ContainerStatus.FAILED
        self.finished_at = time.time()
        self.exit_code = 1

    def restart(self) -> None:
        self.status = ContainerStatus.RESTARTING
        self.restart_count += 1
        self.finished_at = None
        self.exit_code = None
        self.start()

    def simulate_tick(self) -> bool:
        """Advance one simulation tick. Returns False if the container crashed."""
        if self.status != ContainerStatus.RUNNING:
            return True
        if random.random() < self.failure_rate:
            self.fail()
            return False
        return True

    @property
    def uptime_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or time.time()
        return end - self.started_at

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "image": self.image,
            "status": self.status.value,
            "cpu_request": self.cpu_request,
            "memory_request": self.memory_request,
            "restart_count": self.restart_count,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "exit_code": self.exit_code,
        }
