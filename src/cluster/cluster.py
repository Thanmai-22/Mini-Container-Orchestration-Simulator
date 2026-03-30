"""
Cluster Manager — the central orchestrator that ties together nodes,
pods, scheduler, and monitoring into a single simulation engine.
"""

from __future__ import annotations

import random
import time

from src.cluster.node import Node
from src.monitoring.health import HealthMonitor
from src.monitoring.logger import EventLogger
from src.monitoring.metrics import MetricsCollector
from src.pods.container import Container
from src.pods.pod import Pod, PodStatus
from src.scheduler.scheduler import Scheduler


SAMPLE_IMAGES = [
    "nginx:1.25", "redis:7-alpine", "postgres:16", "node:20-slim",
    "python:3.12-slim", "golang:1.22", "mongo:7", "rabbitmq:3.13",
    "elasticsearch:8.12", "grafana/grafana:10.3",
]

SAMPLE_POD_PREFIXES = [
    "web-frontend", "api-gateway", "auth-service", "cache-layer",
    "db-primary", "worker", "ml-inference", "log-aggregator",
    "metrics-exporter", "queue-consumer",
]


class ClusterManager:
    """
    Top-level simulation engine. Provides a tick-based loop:
      1. Advance node simulation (may crash nodes)
      2. Advance pod simulation (may crash containers)
      3. Health check (evict, reschedule, recover)
      4. Schedule any pending pods
      5. Collect metrics
    """

    def __init__(
        self,
        num_nodes: int = 3,
        scheduler_strategy: str = "best-fit",
        node_failure_rate: float = 0.02,
        container_failure_rate: float = 0.05,
    ):
        self.logger = EventLogger()
        self.metrics = MetricsCollector()
        self.scheduler = Scheduler(strategy_name=scheduler_strategy)
        self.health_monitor = HealthMonitor(self.logger)

        self.nodes: list[Node] = []
        self.pods: list[Pod] = []
        self.tick_count = 0
        self.container_failure_rate = container_failure_rate

        for i in range(num_nodes):
            cpu = random.choice([2000, 4000, 8000])
            mem = random.choice([4096, 8192, 16384])
            node = Node(
                name=f"node-{i:02d}",
                cpu_capacity=cpu,
                memory_capacity=mem,
                failure_rate=node_failure_rate,
            )
            self.nodes.append(node)
            self.logger.info(
                "ClusterManager",
                f"Node {node.name} created ({cpu}m CPU, {mem}MB RAM)",
                node_id=node.id,
            )

    def create_pod(
        self,
        name: str | None = None,
        num_containers: int = 1,
        cpu_per_container: int = 200,
        memory_per_container: int = 256,
        namespace: str = "default",
        labels: dict[str, str] | None = None,
        restart_policy: str = "Always",
    ) -> Pod:
        if name is None:
            prefix = random.choice(SAMPLE_POD_PREFIXES)
            name = f"{prefix}-{random.randint(1000, 9999)}"

        containers = []
        for j in range(num_containers):
            c = Container(
                name=f"{name}-c{j}",
                image=random.choice(SAMPLE_IMAGES),
                cpu_request=cpu_per_container,
                memory_request=memory_per_container,
                failure_rate=self.container_failure_rate,
            )
            containers.append(c)

        pod = Pod(
            name=name,
            containers=containers,
            namespace=namespace,
            restart_policy=restart_policy,
            labels=labels or {"app": name.rsplit("-", 1)[0]},
        )
        self.pods.append(pod)
        self.scheduler.enqueue(pod)
        self.logger.info(
            "ClusterManager",
            f"Pod {pod.name} created ({num_containers} containers, "
            f"{cpu_per_container * num_containers}m CPU, "
            f"{memory_per_container * num_containers}MB RAM)",
            pod_id=pod.id,
        )
        return pod

    def delete_pod(self, pod_id: str) -> bool:
        pod = next((p for p in self.pods if p.id == pod_id), None)
        if pod is None:
            return False
        if pod.node_id:
            node = next((n for n in self.nodes if n.id == pod.node_id), None)
            if node:
                node.release(pod.resource_request, pod.id)
        pod.stop()
        self.logger.info("ClusterManager", f"Pod {pod.name} deleted", pod_id=pod.id)
        return True

    def add_node(
        self,
        name: str | None = None,
        cpu_capacity: int = 4000,
        memory_capacity: int = 8192,
    ) -> Node:
        if name is None:
            name = f"node-{len(self.nodes):02d}"
        node = Node(name=name, cpu_capacity=cpu_capacity, memory_capacity=memory_capacity)
        self.nodes.append(node)
        self.logger.info(
            "ClusterManager",
            f"Node {node.name} added ({cpu_capacity}m CPU, {memory_capacity}MB RAM)",
            node_id=node.id,
        )
        return node

    def remove_node(self, node_id: str) -> bool:
        node = next((n for n in self.nodes if n.id == node_id), None)
        if node is None:
            return False

        affected = [p for p in self.pods if p.node_id == node_id and p.is_running]
        for pod in affected:
            node.release(pod.resource_request, pod.id)
            pod.evict()
            self.scheduler.enqueue(pod)
            self.logger.warning(
                "ClusterManager",
                f"Pod {pod.name} evicted — node {node.name} removed",
                pod_id=pod.id, node_id=node.id,
            )

        self.nodes.remove(node)
        self.logger.info("ClusterManager", f"Node {node.name} removed", node_id=node.id)
        return True

    def tick(self) -> dict:
        """Advance the simulation by one step."""
        self.tick_count += 1

        for node in self.nodes:
            node.simulate_tick()

        for pod in self.pods:
            pod.simulate_tick()

        health_report = self.health_monitor.check(
            self.nodes, self.pods, self.scheduler,
        )

        schedule_results = self.scheduler.schedule_pending(self.nodes)
        for result in schedule_results:
            if result.success:
                self.logger.info(
                    "Scheduler",
                    f"Pod {result.pod.name} → {result.node.name} ({self.scheduler.strategy_name})",
                    pod_id=result.pod.id,
                    node_id=result.node.id,
                )
            else:
                self.logger.warning(
                    "Scheduler",
                    f"Pod {result.pod.name} unschedulable: {result.reason}",
                    pod_id=result.pod.id,
                )

        metrics_snap = self.metrics.collect(self.nodes, self.pods)

        return {
            "tick": self.tick_count,
            "health": health_report,
            "scheduled": [r.snapshot() for r in schedule_results],
            "metrics": metrics_snap.snapshot(),
        }

    def set_scheduler_strategy(self, strategy_name: str) -> None:
        self.scheduler.set_strategy(strategy_name)
        self.logger.info(
            "ClusterManager",
            f"Scheduler strategy changed to {strategy_name}",
        )

    def deploy_batch(self, count: int = 5, **pod_kwargs) -> list[Pod]:
        """Deploy multiple pods at once (simulates a Deployment)."""
        pods = []
        for _ in range(count):
            pods.append(self.create_pod(**pod_kwargs))
        return pods

    def snapshot(self) -> dict:
        return {
            "tick": self.tick_count,
            "nodes": [n.snapshot() for n in self.nodes],
            "pods": [p.snapshot() for p in self.pods],
            "scheduler": self.scheduler.snapshot(),
            "metrics": self.metrics.latest,
            "metrics_history": self.metrics.recent(60),
            "events": self.logger.recent(100),
            "event_counts": self.logger.count_by_severity(),
        }
