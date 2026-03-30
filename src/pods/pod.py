"""Pod simulation — a group of co-located containers sharing resources."""

from __future__ import annotations

import time
import uuid
from enum import Enum

from src.cluster.resources import ResourceRequest
from src.pods.container import Container, ContainerStatus


class PodStatus(str, Enum):
    PENDING = "Pending"
    SCHEDULED = "Scheduled"
    RUNNING = "Running"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    EVICTED = "Evicted"


class Pod:
    """
    Models a Kubernetes-style Pod: one or more containers that share
    a network namespace and are scheduled together onto a single node.
    """

    def __init__(
        self,
        name: str,
        containers: list[Container],
        namespace: str = "default",
        restart_policy: str = "Always",
        labels: dict[str, str] | None = None,
    ):
        self.id = str(uuid.uuid4())[:12]
        self.name = name
        self.namespace = namespace
        self.containers = containers
        self.restart_policy = restart_policy
        self.labels = labels or {}

        self.status = PodStatus.PENDING
        self.node_id: str | None = None
        self.created_at = time.time()
        self.scheduled_at: float | None = None
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.restart_count = 0

    @property
    def resource_request(self) -> ResourceRequest:
        total_cpu = sum(c.cpu_request for c in self.containers)
        total_mem = sum(c.memory_request for c in self.containers)
        return ResourceRequest(cpu_millicores=total_cpu, memory_mb=total_mem)

    def schedule_on(self, node_id: str) -> None:
        self.status = PodStatus.SCHEDULED
        self.node_id = node_id
        self.scheduled_at = time.time()

    def start(self) -> None:
        self.status = PodStatus.RUNNING
        self.started_at = time.time()
        for container in self.containers:
            container.start()

    def stop(self) -> None:
        for container in self.containers:
            if container.status == ContainerStatus.RUNNING:
                container.stop()
        self.status = PodStatus.SUCCEEDED
        self.finished_at = time.time()

    def evict(self) -> None:
        for container in self.containers:
            if container.status == ContainerStatus.RUNNING:
                container.stop(exit_code=137)
        self.status = PodStatus.EVICTED
        self.finished_at = time.time()
        self.node_id = None

    def simulate_tick(self) -> None:
        """Advance one simulation tick for every container in this pod."""
        if self.status != PodStatus.RUNNING:
            return

        any_failed = False
        for container in self.containers:
            alive = container.simulate_tick()
            if not alive:
                any_failed = True

        if any_failed:
            if self.restart_policy == "Always":
                for c in self.containers:
                    if c.status == ContainerStatus.FAILED:
                        c.restart()
                        self.restart_count += 1
            elif self.restart_policy == "Never":
                self.status = PodStatus.FAILED
                self.finished_at = time.time()

    @property
    def is_running(self) -> bool:
        return self.status == PodStatus.RUNNING

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
            "namespace": self.namespace,
            "status": self.status.value,
            "node_id": self.node_id,
            "restart_policy": self.restart_policy,
            "labels": self.labels,
            "restart_count": self.restart_count,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "resource_request": {
                "cpu_millicores": self.resource_request.cpu_millicores,
                "memory_mb": self.resource_request.memory_mb,
            },
            "containers": [c.snapshot() for c in self.containers],
            "created_at": self.created_at,
            "scheduled_at": self.scheduled_at,
        }
