"""Metrics collector — gathers point-in-time snapshots of cluster state."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.cluster.node import Node
    from src.pods.pod import Pod


@dataclass
class MetricsSnapshot:
    timestamp: float
    total_nodes: int
    healthy_nodes: int
    total_pods: int
    running_pods: int
    pending_pods: int
    failed_pods: int
    cluster_cpu_utilization: float
    cluster_memory_utilization: float
    total_restarts: int

    def snapshot(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "total_nodes": self.total_nodes,
            "healthy_nodes": self.healthy_nodes,
            "total_pods": self.total_pods,
            "running_pods": self.running_pods,
            "pending_pods": self.pending_pods,
            "failed_pods": self.failed_pods,
            "cluster_cpu_utilization": round(self.cluster_cpu_utilization, 1),
            "cluster_memory_utilization": round(self.cluster_memory_utilization, 1),
            "total_restarts": self.total_restarts,
        }


class MetricsCollector:
    """Periodically samples the cluster and stores historical metrics."""

    def __init__(self, max_history: int = 500) -> None:
        self._history: list[MetricsSnapshot] = []
        self._max = max_history

    def collect(self, nodes: list[Node], pods: list[Pod]) -> MetricsSnapshot:
        from src.cluster.node import NodeStatus
        from src.pods.pod import PodStatus

        healthy = sum(1 for n in nodes if n.status == NodeStatus.READY)

        total_cpu_cap = sum(n.resources.total_cpu for n in nodes) or 1
        total_mem_cap = sum(n.resources.total_memory for n in nodes) or 1
        used_cpu = sum(n.resources.allocated_cpu for n in nodes)
        used_mem = sum(n.resources.allocated_memory for n in nodes)

        snap = MetricsSnapshot(
            timestamp=time.time(),
            total_nodes=len(nodes),
            healthy_nodes=healthy,
            total_pods=len(pods),
            running_pods=sum(1 for p in pods if p.status == PodStatus.RUNNING),
            pending_pods=sum(1 for p in pods if p.status == PodStatus.PENDING),
            failed_pods=sum(1 for p in pods if p.status == PodStatus.FAILED),
            cluster_cpu_utilization=(used_cpu / total_cpu_cap) * 100,
            cluster_memory_utilization=(used_mem / total_mem_cap) * 100,
            total_restarts=sum(p.restart_count for p in pods),
        )
        self._history.append(snap)
        if len(self._history) > self._max:
            self._history = self._history[-self._max:]
        return snap

    def recent(self, count: int = 60) -> list[dict]:
        return [s.snapshot() for s in self._history[-count:]]

    @property
    def latest(self) -> dict | None:
        return self._history[-1].snapshot() if self._history else None
