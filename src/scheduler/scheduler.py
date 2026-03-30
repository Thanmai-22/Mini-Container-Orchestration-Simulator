"""
Central scheduler — binds pending pods to nodes using a pluggable strategy.
Equivalent to kube-scheduler's scheduling cycle (filter → score → bind).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from src.scheduler.strategies import (
    BestFitStrategy,
    FirstFitStrategy,
    LeastLoadedStrategy,
    RoundRobinStrategy,
    SchedulingStrategy,
)

if TYPE_CHECKING:
    from src.cluster.node import Node
    from src.pods.pod import Pod

STRATEGY_MAP: dict[str, type[SchedulingStrategy]] = {
    "first-fit": FirstFitStrategy,
    "best-fit": BestFitStrategy,
    "round-robin": RoundRobinStrategy,
    "least-loaded": LeastLoadedStrategy,
}


class SchedulingResult:
    def __init__(self, pod: Pod, node: Node | None, success: bool, reason: str = ""):
        self.pod = pod
        self.node = node
        self.success = success
        self.reason = reason
        self.timestamp = time.time()

    def snapshot(self) -> dict:
        return {
            "pod_id": self.pod.id,
            "pod_name": self.pod.name,
            "node_id": self.node.id if self.node else None,
            "node_name": self.node.name if self.node else None,
            "success": self.success,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


class Scheduler:
    """
    The scheduler picks a node for every pending pod.

    Workflow mirrors kube-scheduler:
      1. Filter — remove nodes that can't fit the pod
      2. Score  — rank remaining nodes via the chosen strategy
      3. Bind   — assign the pod to the winning node
    """

    def __init__(self, strategy_name: str = "best-fit"):
        self.set_strategy(strategy_name)
        self.history: list[SchedulingResult] = []
        self.pending_queue: list[Pod] = []

    @property
    def strategy_name(self) -> str:
        return self._strategy.name

    def set_strategy(self, name: str) -> None:
        cls = STRATEGY_MAP.get(name)
        if cls is None:
            raise ValueError(
                f"Unknown strategy '{name}'. Choose from: {list(STRATEGY_MAP)}"
            )
        self._strategy = cls()

    def enqueue(self, pod: Pod) -> None:
        self.pending_queue.append(pod)

    def schedule_one(self, pod: Pod, nodes: list[Node]) -> SchedulingResult:
        """Try to schedule a single pod onto a node."""
        request = pod.resource_request
        selected = self._strategy.select_node(nodes, request)

        if selected is None:
            result = SchedulingResult(
                pod, None, success=False,
                reason="No node has sufficient resources",
            )
            self.history.append(result)
            return result

        allocated = selected.allocate(request, pod.id)
        if not allocated:
            result = SchedulingResult(
                pod, selected, success=False,
                reason=f"Allocation failed on {selected.name}",
            )
            self.history.append(result)
            return result

        pod.schedule_on(selected.id)
        pod.start()
        result = SchedulingResult(
            pod, selected, success=True,
            reason=f"Bound to {selected.name} via {self.strategy_name}",
        )
        self.history.append(result)
        return result

    def schedule_pending(self, nodes: list[Node]) -> list[SchedulingResult]:
        """Drain the pending queue and schedule everything possible."""
        results: list[SchedulingResult] = []
        still_pending: list[Pod] = []

        for pod in self.pending_queue:
            result = self.schedule_one(pod, nodes)
            results.append(result)
            if not result.success:
                still_pending.append(pod)

        self.pending_queue = still_pending
        return results

    def snapshot(self) -> dict:
        return {
            "strategy": self.strategy_name,
            "pending_count": len(self.pending_queue),
            "total_scheduled": sum(1 for r in self.history if r.success),
            "total_failed": sum(1 for r in self.history if not r.success),
            "recent_history": [r.snapshot() for r in self.history[-20:]],
        }
