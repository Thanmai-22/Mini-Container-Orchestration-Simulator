"""Tests for Pod and Container lifecycle."""

from src.pods.container import Container, ContainerStatus
from src.pods.pod import Pod, PodStatus


class TestContainer:
    def test_lifecycle(self):
        c = Container("c1", "nginx:1.25", failure_rate=0)
        assert c.status == ContainerStatus.CREATED
        c.start()
        assert c.status == ContainerStatus.RUNNING
        c.stop()
        assert c.status == ContainerStatus.TERMINATED
        assert c.exit_code == 0

    def test_failure_and_restart(self):
        c = Container("c1", "nginx:1.25", failure_rate=0)
        c.start()
        c.fail()
        assert c.status == ContainerStatus.FAILED
        c.restart()
        assert c.status == ContainerStatus.RUNNING
        assert c.restart_count == 1

    def test_no_crash_when_failure_rate_zero(self):
        c = Container("c1", "nginx:1.25", failure_rate=0)
        c.start()
        for _ in range(100):
            assert c.simulate_tick() is True
        assert c.status == ContainerStatus.RUNNING


class TestPod:
    def test_pod_aggregates_resources(self):
        containers = [
            Container("c1", "img", cpu_request=200, memory_request=256),
            Container("c2", "img", cpu_request=300, memory_request=512),
        ]
        pod = Pod("multi", containers)
        req = pod.resource_request
        assert req.cpu_millicores == 500
        assert req.memory_mb == 768

    def test_schedule_and_start(self):
        c = Container("c1", "img", failure_rate=0)
        pod = Pod("test-pod", [c])
        assert pod.status == PodStatus.PENDING
        pod.schedule_on("node-xyz")
        assert pod.status == PodStatus.SCHEDULED
        pod.start()
        assert pod.status == PodStatus.RUNNING
        assert c.status == ContainerStatus.RUNNING

    def test_evict(self):
        c = Container("c1", "img", failure_rate=0)
        pod = Pod("test-pod", [c])
        pod.schedule_on("node-1")
        pod.start()
        pod.evict()
        assert pod.status == PodStatus.EVICTED
        assert pod.node_id is None

    def test_restart_policy_always(self):
        c = Container("c1", "img", failure_rate=1.0)
        pod = Pod("test-pod", [c], restart_policy="Always")
        pod.schedule_on("node-1")
        pod.start()
        pod.simulate_tick()
        assert c.status == ContainerStatus.RUNNING
        assert c.restart_count >= 1

    def test_restart_policy_never(self):
        c = Container("c1", "img", failure_rate=1.0)
        pod = Pod("test-pod", [c], restart_policy="Never")
        pod.schedule_on("node-1")
        pod.start()
        pod.simulate_tick()
        assert pod.status == PodStatus.FAILED
