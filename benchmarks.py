"""
Performance benchmarks for the Mini Container Orchestration Simulator.

Measures scheduling latency, throughput, resource utilization efficiency,
and failure recovery time across all four scheduling strategies.

Usage:
    python benchmarks.py
"""

from __future__ import annotations

import statistics
import time

from src.cluster.cluster import ClusterManager
from src.cluster.node import Node, NodeStatus
from src.pods.container import Container
from src.pods.pod import Pod, PodStatus
from src.scheduler.scheduler import Scheduler


def benchmark_scheduling_latency(strategy: str, num_pods: int = 200) -> dict:
    """Measure per-pod scheduling decision time for a given strategy."""
    nodes = [
        Node(f"node-{i}", cpu_capacity=8000, memory_capacity=16384, failure_rate=0)
        for i in range(5)
    ]
    scheduler = Scheduler(strategy_name=strategy)
    latencies: list[float] = []

    for i in range(num_pods):
        c = Container(f"bench-{i}-c0", "nginx:1.25", cpu_request=100, memory_request=128, failure_rate=0)
        pod = Pod(f"bench-{i}", [c])

        start = time.perf_counter_ns()
        scheduler.schedule_one(pod, nodes)
        elapsed_ns = time.perf_counter_ns() - start

        latencies.append(elapsed_ns / 1_000)  # convert to microseconds

    return {
        "strategy": strategy,
        "pods_scheduled": num_pods,
        "avg_latency_us": round(statistics.mean(latencies), 2),
        "p50_latency_us": round(statistics.median(latencies), 2),
        "p99_latency_us": round(sorted(latencies)[int(num_pods * 0.99)], 2),
        "max_latency_us": round(max(latencies), 2),
    }


def benchmark_throughput(strategy: str, duration_seconds: float = 2.0) -> dict:
    """Measure how many pods can be scheduled per second."""
    nodes = [
        Node(f"node-{i}", cpu_capacity=100_000, memory_capacity=500_000, failure_rate=0)
        for i in range(10)
    ]
    scheduler = Scheduler(strategy_name=strategy)
    count = 0
    start = time.perf_counter()

    while (time.perf_counter() - start) < duration_seconds:
        c = Container(f"tp-{count}-c0", "nginx", cpu_request=10, memory_request=10, failure_rate=0)
        pod = Pod(f"tp-{count}", [c])
        scheduler.schedule_one(pod, nodes)
        count += 1

    elapsed = time.perf_counter() - start
    return {
        "strategy": strategy,
        "total_scheduled": count,
        "duration_seconds": round(elapsed, 2),
        "pods_per_second": round(count / elapsed),
    }


def benchmark_utilization_efficiency(strategy: str) -> dict:
    """
    Measure how efficiently each strategy packs pods onto nodes.
    Deploy pods until the cluster is full, then measure utilization.
    """
    cm = ClusterManager(num_nodes=4, scheduler_strategy=strategy,
                        node_failure_rate=0, container_failure_rate=0)

    scheduled = 0
    failed = 0
    for i in range(100):
        pod = cm.create_pod(
            name=f"util-{i}",
            cpu_per_container=150 + (i % 5) * 50,  # varied sizes: 150-350m
            memory_per_container=128 + (i % 4) * 64,  # varied: 128-320MB
        )
        result = cm.tick()
        running = sum(1 for p in cm.pods if p.status == PodStatus.RUNNING)
        pending = sum(1 for p in cm.pods if p.status == PodStatus.PENDING)
        if pending > 0 and running == scheduled:
            failed += 1
            if failed >= 3:
                break
        else:
            scheduled = running

    total_cpu = sum(n.resources.total_cpu for n in cm.nodes)
    total_mem = sum(n.resources.total_memory for n in cm.nodes)
    used_cpu = sum(n.resources.allocated_cpu for n in cm.nodes)
    used_mem = sum(n.resources.allocated_memory for n in cm.nodes)

    node_utils = []
    for n in cm.nodes:
        node_utils.append(n.resources.overall_utilization)
    balance_stddev = statistics.stdev(node_utils) if len(node_utils) > 1 else 0

    return {
        "strategy": strategy,
        "pods_placed": scheduled,
        "cpu_utilization_pct": round((used_cpu / total_cpu) * 100, 1),
        "memory_utilization_pct": round((used_mem / total_mem) * 100, 1),
        "load_balance_stddev": round(balance_stddev, 4),
    }


def benchmark_failure_recovery() -> dict:
    """
    Measure how quickly evicted pods get rescheduled after a node failure.
    """
    cm = ClusterManager(num_nodes=4, scheduler_strategy="least-loaded",
                        node_failure_rate=0, container_failure_rate=0)
    cm.deploy_batch(count=12, cpu_per_container=200, memory_per_container=256)

    for _ in range(3):
        cm.tick()

    running_before = sum(1 for p in cm.pods if p.status == PodStatus.RUNNING)

    target_node = max(cm.nodes, key=lambda n: len(n.pod_ids))
    evicted_count = len(target_node.pod_ids)
    target_node.status = NodeStatus.FAILED

    ticks_to_recover = 0
    for _ in range(20):
        cm.tick()
        ticks_to_recover += 1
        running_now = sum(1 for p in cm.pods if p.status == PodStatus.RUNNING)
        if running_now >= running_before:
            break

    running_after = sum(1 for p in cm.pods if p.status == PodStatus.RUNNING)

    return {
        "pods_before_failure": running_before,
        "pods_evicted": evicted_count,
        "ticks_to_full_recovery": ticks_to_recover,
        "pods_recovered": running_after,
        "recovery_rate_pct": round((running_after / running_before) * 100, 1) if running_before > 0 else 0,
    }


def benchmark_resource_fragmentation() -> dict:
    """
    Measure resource fragmentation — wasted capacity due to uneven allocation.
    Compare Best Fit (packs tight) vs Round Robin (spreads evenly).
    """
    results = {}
    for strategy in ["best-fit", "round-robin"]:
        cm = ClusterManager(num_nodes=4, scheduler_strategy=strategy,
                            node_failure_rate=0, container_failure_rate=0)
        for i in range(30):
            cpu = [100, 200, 400, 150, 300][i % 5]
            mem = [128, 256, 512, 192, 384][i % 5]
            cm.create_pod(name=f"frag-{i}", cpu_per_container=cpu, memory_per_container=mem)
            cm.tick()

        fragments = []
        for n in cm.nodes:
            avail_cpu = n.resources.available_cpu
            avail_mem = n.resources.available_memory
            can_fit_small = min(avail_cpu // 100, avail_mem // 128)
            fragments.append({
                "node": n.name,
                "wasted_cpu": avail_cpu,
                "wasted_mem": avail_mem,
                "could_fit_small_pods": can_fit_small,
            })

        total_wasted_cpu = sum(f["wasted_cpu"] for f in fragments)
        total_cpu = sum(n.resources.total_cpu for n in cm.nodes)

        results[strategy] = {
            "strategy": strategy,
            "fragmentation_pct": round((total_wasted_cpu / total_cpu) * 100, 1),
            "per_node": fragments,
        }
    return results


def main():
    print("=" * 70)
    print("  MINI K8S ORCHESTRATOR - PERFORMANCE BENCHMARKS")
    print("=" * 70)

    # 1. Scheduling Latency
    print("\n--- Scheduling Latency (200 pods, 5 nodes) ---\n")
    print(f"  {'Strategy':<15} {'Avg (us)':<12} {'P50 (us)':<12} {'P99 (us)':<12} {'Max (us)':<12}")
    print(f"  {'-'*63}")
    latency_results = {}
    for strategy in ["first-fit", "best-fit", "round-robin", "least-loaded"]:
        r = benchmark_scheduling_latency(strategy)
        latency_results[strategy] = r
        print(f"  {r['strategy']:<15} {r['avg_latency_us']:<12} {r['p50_latency_us']:<12} {r['p99_latency_us']:<12} {r['max_latency_us']:<12}")

    # 2. Throughput
    print("\n--- Scheduling Throughput (2s burst, 10 nodes) ---\n")
    print(f"  {'Strategy':<15} {'Total':<12} {'Pods/sec':<12}")
    print(f"  {'-'*39}")
    throughput_results = {}
    for strategy in ["first-fit", "best-fit", "round-robin", "least-loaded"]:
        r = benchmark_throughput(strategy)
        throughput_results[strategy] = r
        print(f"  {r['strategy']:<15} {r['total_scheduled']:<12} {r['pods_per_second']:<12}")

    # 3. Utilization Efficiency
    print("\n--- Resource Utilization Efficiency (varied pod sizes, 4 nodes) ---\n")
    print(f"  {'Strategy':<15} {'Pods Placed':<13} {'CPU %':<10} {'MEM %':<10} {'Balance SD':<12}")
    print(f"  {'-'*60}")
    util_results = {}
    for strategy in ["first-fit", "best-fit", "round-robin", "least-loaded"]:
        r = benchmark_utilization_efficiency(strategy)
        util_results[strategy] = r
        print(f"  {r['strategy']:<15} {r['pods_placed']:<13} {r['cpu_utilization_pct']:<10} {r['memory_utilization_pct']:<10} {r['load_balance_stddev']:<12}")

    # 4. Failure Recovery
    print("\n--- Failure Recovery (kill busiest node) ---\n")
    rec = benchmark_failure_recovery()
    print(f"  Pods before failure:   {rec['pods_before_failure']}")
    print(f"  Pods evicted:          {rec['pods_evicted']}")
    print(f"  Ticks to recover:      {rec['ticks_to_full_recovery']}")
    print(f"  Pods after recovery:   {rec['pods_recovered']}")
    print(f"  Recovery rate:         {rec['recovery_rate_pct']}%")

    # 5. Fragmentation
    print("\n--- Resource Fragmentation (Best Fit vs Round Robin) ---\n")
    frag = benchmark_resource_fragmentation()
    for s in ["best-fit", "round-robin"]:
        f = frag[s]
        print(f"  {s:<15} Fragmentation: {f['fragmentation_pct']}%")

    print("\n" + "=" * 70)
    print("  Benchmark complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
