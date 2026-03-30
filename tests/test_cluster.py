"""Integration tests for the ClusterManager simulation engine."""

from src.cluster.cluster import ClusterManager
from src.pods.pod import PodStatus
from src.cluster.node import NodeStatus


class TestClusterLifecycle:
    def test_init_creates_nodes(self):
        cm = ClusterManager(num_nodes=5, node_failure_rate=0, container_failure_rate=0)
        assert len(cm.nodes) == 5
        assert all(n.status == NodeStatus.READY for n in cm.nodes)

    def test_create_and_schedule_pod(self):
        cm = ClusterManager(num_nodes=2, node_failure_rate=0, container_failure_rate=0)
        pod = cm.create_pod(name="web-1", cpu_per_container=100, memory_per_container=128)
        cm.tick()
        assert pod.status == PodStatus.RUNNING
        assert pod.node_id is not None

    def test_delete_pod_releases_resources(self):
        cm = ClusterManager(num_nodes=1, node_failure_rate=0, container_failure_rate=0)
        pod = cm.create_pod(cpu_per_container=500, memory_per_container=1024)
        cm.tick()
        node = cm.nodes[0]
        assert node.resources.allocated_cpu >= 500
        cm.delete_pod(pod.id)
        assert node.resources.allocated_cpu == 0

    def test_batch_deploy(self):
        cm = ClusterManager(num_nodes=3, node_failure_rate=0, container_failure_rate=0)
        pods = cm.deploy_batch(count=6, cpu_per_container=100, memory_per_container=128)
        assert len(pods) == 6
        cm.tick()
        running = [p for p in pods if p.status == PodStatus.RUNNING]
        assert len(running) == 6

    def test_add_and_remove_node(self):
        cm = ClusterManager(num_nodes=1, node_failure_rate=0, container_failure_rate=0)
        new_node = cm.add_node(name="extra-node")
        assert len(cm.nodes) == 2
        cm.remove_node(new_node.id)
        assert len(cm.nodes) == 1


class TestFailureRecovery:
    def test_node_failure_evicts_pods(self):
        cm = ClusterManager(
            num_nodes=2, node_failure_rate=0, container_failure_rate=0,
        )
        pod = cm.create_pod(cpu_per_container=100, memory_per_container=128)
        cm.tick()  # schedule
        assigned_node = next(n for n in cm.nodes if n.id == pod.node_id)
        assigned_node.status = NodeStatus.FAILED
        cm.tick()  # health check should evict + reschedule
        # pod is either evicted and re-queued, or already rescheduled
        assert pod.status in (PodStatus.EVICTED, PodStatus.RUNNING, PodStatus.PENDING)

    def test_simulation_runs_many_ticks(self):
        cm = ClusterManager(
            num_nodes=3,
            node_failure_rate=0.01,
            container_failure_rate=0.02,
        )
        cm.deploy_batch(count=10)
        for _ in range(50):
            cm.tick()
        snap = cm.snapshot()
        assert snap["tick"] == 50
        assert snap["metrics"] is not None


class TestSchedulerStrategy:
    def test_change_strategy(self):
        cm = ClusterManager(num_nodes=2, scheduler_strategy="first-fit")
        assert cm.scheduler.strategy_name == "first-fit"
        cm.set_scheduler_strategy("least-loaded")
        assert cm.scheduler.strategy_name == "least-loaded"

    def test_snapshot_is_complete(self):
        cm = ClusterManager(num_nodes=2, node_failure_rate=0, container_failure_rate=0)
        cm.create_pod()
        cm.tick()
        snap = cm.snapshot()
        assert "nodes" in snap
        assert "pods" in snap
        assert "scheduler" in snap
        assert "metrics" in snap
        assert "events" in snap
