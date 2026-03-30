"""
Scheduling strategies — pluggable algorithms that decide which node
receives a given pod. Mirrors real kube-scheduler's scoring/filtering model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.cluster.node import Node
    from src.cluster.resources import ResourceRequest


class SchedulingStrategy(ABC):
    """Base class for all scheduling strategies."""

    name: str = "base"

    @abstractmethod
    def select_node(self, nodes: list[Node], request: ResourceRequest) -> Node | None:
        ...

    def _filter_eligible(self, nodes: list[Node], request: ResourceRequest) -> list[Node]:
        return [n for n in nodes if n.can_fit(request)]


class FirstFitStrategy(SchedulingStrategy):
    """Pick the first node that has enough resources — fast but naive."""

    name = "first-fit"

    def select_node(self, nodes: list[Node], request: ResourceRequest) -> Node | None:
        eligible = self._filter_eligible(nodes, request)
        return eligible[0] if eligible else None


class BestFitStrategy(SchedulingStrategy):
    """
    Pick the node where the pod fits most tightly (least remaining resources
    after allocation). Packs bins efficiently, maximising cluster density.
    """

    name = "best-fit"

    def select_node(self, nodes: list[Node], request: ResourceRequest) -> Node | None:
        eligible = self._filter_eligible(nodes, request)
        if not eligible:
            return None
        return min(
            eligible,
            key=lambda n: (
                n.resources.available_cpu - request.cpu_millicores
                + n.resources.available_memory - request.memory_mb
            ),
        )


class RoundRobinStrategy(SchedulingStrategy):
    """Cycle through eligible nodes in order for even distribution."""

    name = "round-robin"

    def __init__(self) -> None:
        self._index = 0

    def select_node(self, nodes: list[Node], request: ResourceRequest) -> Node | None:
        eligible = self._filter_eligible(nodes, request)
        if not eligible:
            return None
        node = eligible[self._index % len(eligible)]
        self._index += 1
        return node


class LeastLoadedStrategy(SchedulingStrategy):
    """Pick the node with the lowest overall utilisation — spreads the load."""

    name = "least-loaded"

    def select_node(self, nodes: list[Node], request: ResourceRequest) -> Node | None:
        eligible = self._filter_eligible(nodes, request)
        if not eligible:
            return None
        return min(eligible, key=lambda n: n.resources.overall_utilization)
