"""
Health monitor — watches nodes and pods, detects failures,
and triggers automatic recovery (rescheduling crashed pods).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.monitoring.logger import EventLogger

if TYPE_CHECKING:
    from src.cluster.node import Node
    from src.pods.pod import Pod
    from src.scheduler.scheduler import Scheduler


class HealthMonitor:
    """
    Runs every simulation tick to:
      1. Detect crashed nodes
      2. Evict pods from failed nodes
      3. Re-enqueue evicted pods for rescheduling
      4. Optionally auto-recover nodes after a cooldown
    """

    def __init__(self, logger: EventLogger, auto_recover_nodes: bool = True):
        self.logger = logger
        self.auto_recover = auto_recover_nodes
        self._tick_count = 0
        self._recover_after_ticks = 5

    def check(
        self,
        nodes: list[Node],
        pods: list[Pod],
        scheduler: Scheduler,
    ) -> dict:
        from src.cluster.node import NodeStatus
        from src.pods.pod import PodStatus

        self._tick_count += 1
        report = {
            "failed_nodes": [],
            "evicted_pods": [],
            "recovered_nodes": [],
            "restarted_containers": 0,
        }

        for node in nodes:
            if node.status == NodeStatus.FAILED:
                if node.id not in [r["node_id"] for r in report["failed_nodes"]]:
                    report["failed_nodes"].append({
                        "node_id": node.id,
                        "node_name": node.name,
                    })
                    self.logger.critical(
                        "HealthMonitor",
                        f"Node {node.name} has FAILED",
                        node_id=node.id,
                    )

                affected_pods = [p for p in pods if p.node_id == node.id and p.is_running]
                for pod in affected_pods:
                    node.release(pod.resource_request, pod.id)
                    pod.evict()
                    scheduler.enqueue(pod)
                    report["evicted_pods"].append({
                        "pod_id": pod.id,
                        "pod_name": pod.name,
                    })
                    self.logger.warning(
                        "HealthMonitor",
                        f"Pod {pod.name} evicted from failed node {node.name}, re-queued",
                        pod_id=pod.id, node_id=node.id,
                    )

        for pod in pods:
            if pod.status == PodStatus.RUNNING:
                for container in pod.containers:
                    from src.pods.container import ContainerStatus
                    if container.status == ContainerStatus.FAILED:
                        report["restarted_containers"] += 1

        if self.auto_recover and self._tick_count % self._recover_after_ticks == 0:
            for node in nodes:
                if node.status == NodeStatus.FAILED:
                    node.recover()
                    report["recovered_nodes"].append({
                        "node_id": node.id,
                        "node_name": node.name,
                    })
                    self.logger.info(
                        "HealthMonitor",
                        f"Node {node.name} has recovered and is Ready",
                        node_id=node.id,
                    )

        return report
