"""
Mini Container Orchestration Simulator
=======================================
Entry point — start the API server with a live dashboard, or run a
headless CLI simulation to see scheduling + failover in the terminal.

Usage:
    python main.py server          # Launch web dashboard on http://localhost:8000
    python main.py server --port 9000
    python main.py demo            # Run a headless CLI demo
"""

from __future__ import annotations

import argparse
import sys
import time


def run_server(host: str, port: int) -> None:
    import uvicorn
    from src.api.server import app

    print(f"\n  Mini K8s Orchestrator  —  http://{host}:{port}\n")
    uvicorn.run(app, host=host, port=port, log_level="info")


def run_demo() -> None:
    """Headless CLI demo — shows scheduling, resource allocation, and failover."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich.live import Live
        from rich.layout import Layout
        HAS_RICH = True
    except ImportError:
        HAS_RICH = False

    from src.cluster.cluster import ClusterManager

    cluster = ClusterManager(
        num_nodes=4,
        scheduler_strategy="best-fit",
        node_failure_rate=0.03,
        container_failure_rate=0.04,
    )

    cluster.deploy_batch(count=8, cpu_per_container=300, memory_per_container=512)

    if HAS_RICH:
        _rich_demo(cluster)
    else:
        _plain_demo(cluster)


def _plain_demo(cluster) -> None:
    print("\n=== Mini K8s Orchestrator — CLI Demo ===\n")
    print(f"Nodes: {len(cluster.nodes)}  |  Pods: {len(cluster.pods)}")
    print(f"Scheduler: {cluster.scheduler.strategy_name}\n")
    print("Running 30 simulation ticks …\n")

    for i in range(30):
        result = cluster.tick()
        m = result["metrics"]

        if i % 5 == 0 and i < 20:
            cluster.create_pod(cpu_per_container=200, memory_per_container=256)

        line = (
            f"Tick {result['tick']:>3d}  │  "
            f"Nodes {m['healthy_nodes']}/{m['total_nodes']}  │  "
            f"Pods {m['running_pods']} run / {m['pending_pods']} pend / {m['failed_pods']} fail  │  "
            f"CPU {m['cluster_cpu_utilization']:5.1f}%  │  "
            f"MEM {m['cluster_memory_utilization']:5.1f}%  │  "
            f"Restarts {m['total_restarts']}"
        )
        print(line)
        time.sleep(0.3)

    print("\n── Final Cluster State ─────────────────────────")
    snap = cluster.snapshot()
    for node in snap["nodes"]:
        r = node["resources"]
        print(
            f"  {node['name']:>10s}  {node['status']:>10s}  "
            f"CPU {r['cpu_utilization']:5.1f}%  MEM {r['memory_utilization']:5.1f}%  "
            f"Pods: {node['pod_count']}"
        )
    print()
    for evt in snap["events"][-10:]:
        print(f"  [{evt['severity']:>8s}] {evt['source']}: {evt['message']}")
    print("\nDone.\n")


def _rich_demo(cluster) -> None:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    from rich.text import Text

    console = Console()
    console.print(Panel.fit(
        "[bold cyan]Mini K8s Orchestrator[/bold cyan] — CLI Demo",
        subtitle=f"{len(cluster.nodes)} nodes · {len(cluster.pods)} pods · {cluster.scheduler.strategy_name}",
    ))

    with Live(console=console, refresh_per_second=4) as live:
        for i in range(30):
            result = cluster.tick()
            m = result["metrics"]

            if i % 5 == 0 and i < 20:
                cluster.create_pod(cpu_per_container=200, memory_per_container=256)

            table = Table(title=f"Tick {result['tick']}", expand=True)
            table.add_column("Node", style="cyan", width=12)
            table.add_column("Status", width=10)
            table.add_column("CPU", justify="right", width=8)
            table.add_column("MEM", justify="right", width=8)
            table.add_column("Pods", justify="right", width=6)

            snap = cluster.snapshot()
            for node in snap["nodes"]:
                r = node["resources"]
                status_style = {
                    "Ready": "green", "Failed": "red",
                    "Cordoned": "yellow", "NotReady": "yellow",
                }.get(node["status"], "white")
                table.add_row(
                    node["name"],
                    f"[{status_style}]{node['status']}[/{status_style}]",
                    f"{r['cpu_utilization']:.0f}%",
                    f"{r['memory_utilization']:.0f}%",
                    str(node["pod_count"]),
                )

            summary = Text.assemble(
                ("  Pods: ", "bold"),
                (f"{m['running_pods']} running", "green"),
                (" · ", "dim"),
                (f"{m['pending_pods']} pending", "yellow"),
                (" · ", "dim"),
                (f"{m['failed_pods']} failed", "red"),
                ("  │  Restarts: ", "bold"),
                (f"{m['total_restarts']}", "magenta"),
            )

            from rich.console import Group
            live.update(Group(table, summary))
            time.sleep(0.4)

    console.print("\n[bold]Event Log (last 10):[/bold]")
    for evt in cluster.snapshot()["events"][-10:]:
        sev_color = {"INFO": "blue", "WARNING": "yellow", "ERROR": "red", "CRITICAL": "red bold"}.get(evt["severity"], "white")
        console.print(f"  [{sev_color}]{evt['severity']:>8s}[/{sev_color}]  {evt['source']}: {evt['message']}")
    console.print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mini Container Orchestration Simulator",
    )
    sub = parser.add_subparsers(dest="command")

    srv = sub.add_parser("server", help="Launch the web dashboard")
    srv.add_argument("--host", default="0.0.0.0")
    srv.add_argument("--port", type=int, default=8000)

    sub.add_parser("demo", help="Run a headless CLI demo")

    args = parser.parse_args()

    if args.command == "server":
        run_server(args.host, args.port)
    elif args.command == "demo":
        run_demo()
    else:
        parser.print_help()
        print("\nQuick start:")
        print("  python main.py server    # web dashboard at http://localhost:8000")
        print("  python main.py demo      # CLI demo\n")


if __name__ == "__main__":
    main()
