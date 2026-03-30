"""Tests for scheduler strategies and scheduling workflow."""

import pytest
from src.cluster.node import Node
from src.pods.pod import Pod, PodStatus
from src.pods.container import Container
from src.scheduler.scheduler import Scheduler


def _make_nodes():
    """Create three nodes with different capacities."""
    return [
        Node("small", cpu_capacity=1000, memory_capacity=2048, failure_rate=0),
        Node("medium", cpu_capacity=4000, memory_capacity=8192, failure_rate=0),
        Node("large", cpu_capacity=8000, memory_capacity=16384, failure_rate=0),
    ]


def _make_pod(name="test-pod", cpu=200, mem=256):
    c = Container(name=f"{name}-c0", image="nginx:1.25",
                  cpu_request=cpu, memory_request=mem, failure_rate=0)
    return Pod(name=name, containers=[c])


class TestFirstFit:
    def test_picks_first_eligible(self):
        scheduler = Scheduler(strategy_name="first-fit")
        nodes = _make_nodes()
        pod = _make_pod()
        result = scheduler.schedule_one(pod, nodes)
        assert result.success is True
        assert result.node.name == "small"

    def test_skips_full_nodes(self):
        scheduler = Scheduler(strategy_name="first-fit")
        nodes = _make_nodes()
        # fill the small node
        for i in range(5):
            p = _make_pod(f"fill-{i}", cpu=200, mem=400)
            scheduler.schedule_one(p, nodes)
        pod = _make_pod("overflow", cpu=200, mem=400)
        result = scheduler.schedule_one(pod, nodes)
        assert result.success is True
        assert result.node.name != "small"


class TestBestFit:
    def test_packs_tightly(self):
        scheduler = Scheduler(strategy_name="best-fit")
        nodes = _make_nodes()
        pod = _make_pod(cpu=800, mem=1800)
        result = scheduler.schedule_one(pod, nodes)
        assert result.success is True
        assert result.node.name == "small"


class TestLeastLoaded:
    def test_spreads_evenly(self):
        scheduler = Scheduler(strategy_name="least-loaded")
        nodes = _make_nodes()
        names = []
        for i in range(3):
            pod = _make_pod(f"p{i}", cpu=100, mem=128)
            result = scheduler.schedule_one(pod, nodes)
            assert result.success
            names.append(result.node.name)
        # least-loaded should spread across all nodes
        assert len(set(names)) > 1


class TestSchedulerQueue:
    def test_pending_queue_drains(self):
        scheduler = Scheduler(strategy_name="best-fit")
        nodes = _make_nodes()
        for i in range(3):
            scheduler.enqueue(_make_pod(f"q{i}"))
        assert len(scheduler.pending_queue) == 3
        results = scheduler.schedule_pending(nodes)
        assert all(r.success for r in results)
        assert len(scheduler.pending_queue) == 0

    def test_unschedulable_stays_in_queue(self):
        scheduler = Scheduler(strategy_name="first-fit")
        tiny_node = [Node("tiny", cpu_capacity=100, memory_capacity=128, failure_rate=0)]
        big_pod = _make_pod("big", cpu=5000, mem=10000)
        scheduler.enqueue(big_pod)
        scheduler.schedule_pending(tiny_node)
        assert len(scheduler.pending_queue) == 1
        assert big_pod.status == PodStatus.PENDING
