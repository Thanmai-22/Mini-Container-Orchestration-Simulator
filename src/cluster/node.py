"""Node simulation — represents a worker machine in the cluster."""

from __future__ import annotations

import random
import time
import uuid
from enum import Enum

from src.cluster.resources import ResourcePool, ResourceRequest


class NodeStatus(str, Enum):
    READY = "Ready"
    NOT_READY = "NotReady"
    CORDONED = "Cordoned"
    FAILED = "Failed"


class Node:
    """
    Models a cluster node (worker machine) with finite CPU/memory resources.
    Nodes can fail, be cordoned, and recover — just like real K8s nodes.
    """

    def __init__(
        self,
        name: str,
        cpu_capacity: int = 4000,
        memory_capacity: int = 8192,
        failure_rate: float = 0.02,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.failure_rate = failure_rate
        self.status = NodeStatus.READY
        self.resources = ResourcePool(
            total_cpu=cpu_capacity,
            total_memory=memory_capacity,
        )
        self.pod_ids: list[str] = []
        self.created_at = time.time()
        self.last_heartbeat = time.time()
        self.conditions: list[dict] = []

    @property
    def is_schedulable(self) -> bool:
        return self.status == NodeStatus.READY

    def can_fit(self, request: ResourceRequest) -> bool:
        return self.is_schedulable and request.fits_within(self.resources)

    def allocate(self, request: ResourceRequest, pod_id: str) -> bool:
        if not self.can_fit(request):
            return False
        self.resources.allocate(request, pod_id)
        self.pod_ids.append(pod_id)
        return True

    def release(self, request: ResourceRequest, pod_id: str) -> None:
        self.resources.release(request, pod_id)
        if pod_id in self.pod_ids:
            self.pod_ids.remove(pod_id)

    def cordon(self) -> None:
        self.status = NodeStatus.CORDONED
        self.conditions.append({"type": "Cordoned", "time": time.time()})

    def uncordon(self) -> None:
        self.status = NodeStatus.READY
        self.conditions.append({"type": "Uncordoned", "time": time.time()})

    def heartbeat(self) -> None:
        self.last_heartbeat = time.time()

    def simulate_tick(self) -> bool:
        """Returns False if the node crashes during this tick."""
        if self.status == NodeStatus.FAILED:
            return False
        if self.status in (NodeStatus.READY, NodeStatus.CORDONED):
            if random.random() < self.failure_rate:
                self.status = NodeStatus.FAILED
                self.conditions.append({"type": "NodeFailed", "time": time.time()})
                return False
            self.heartbeat()
        return True

    def recover(self) -> None:
        self.status = NodeStatus.READY
        self.last_heartbeat = time.time()
        self.conditions.append({"type": "Recovered", "time": time.time()})

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "pod_count": len(self.pod_ids),
            "pod_ids": list(self.pod_ids),
            "resources": self.resources.snapshot(),
            "created_at": self.created_at,
            "last_heartbeat": self.last_heartbeat,
            "failure_rate": self.failure_rate,
        }
