"""
FastAPI server with REST endpoints and WebSocket for real-time dashboard updates.
"""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.cluster.cluster import ClusterManager

app = FastAPI(
    title="Mini Container Orchestration Simulator",
    description="A Kubernetes-style container scheduler and cluster simulator",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

cluster: ClusterManager | None = None
simulation_task: asyncio.Task | None = None
simulation_running = False
connected_clients: list[WebSocket] = []


class ClusterConfig(BaseModel):
    num_nodes: int = 3
    scheduler_strategy: str = "best-fit"
    node_failure_rate: float = 0.02
    container_failure_rate: float = 0.05


class PodConfig(BaseModel):
    name: str | None = None
    num_containers: int = 1
    cpu_per_container: int = 200
    memory_per_container: int = 256
    namespace: str = "default"
    restart_policy: str = "Always"


class BatchConfig(BaseModel):
    count: int = 5
    cpu_per_container: int = 200
    memory_per_container: int = 256
    num_containers: int = 1


class NodeConfig(BaseModel):
    name: str | None = None
    cpu_capacity: int = 4000
    memory_capacity: int = 8192


class StrategyConfig(BaseModel):
    strategy: str


def get_cluster() -> ClusterManager:
    global cluster
    if cluster is None:
        cluster = ClusterManager()
    return cluster


async def broadcast(data: dict) -> None:
    dead: list[WebSocket] = []
    message = json.dumps(data, default=str)
    for ws in connected_clients:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connected_clients.remove(ws)


async def simulation_loop(tick_interval: float = 1.0) -> None:
    global simulation_running
    while simulation_running:
        c = get_cluster()
        result = c.tick()
        await broadcast({"type": "tick", "data": result, "state": c.snapshot()})
        await asyncio.sleep(tick_interval)


# ── REST Endpoints ──────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    import os
    dashboard_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "dashboard", "index.html"
    )
    with open(dashboard_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.post("/api/cluster/init")
async def init_cluster(config: ClusterConfig):
    global cluster
    cluster = ClusterManager(
        num_nodes=config.num_nodes,
        scheduler_strategy=config.scheduler_strategy,
        node_failure_rate=config.node_failure_rate,
        container_failure_rate=config.container_failure_rate,
    )
    return {"status": "ok", "state": cluster.snapshot()}


@app.get("/api/cluster/state")
async def cluster_state():
    return get_cluster().snapshot()


@app.post("/api/cluster/tick")
async def manual_tick():
    c = get_cluster()
    result = c.tick()
    return {"tick_result": result, "state": c.snapshot()}


@app.post("/api/simulation/start")
async def start_simulation(tick_interval: float = Query(default=1.0)):
    global simulation_task, simulation_running
    if simulation_running:
        return {"status": "already running"}
    c = get_cluster()
    if not c.pods:
        c.deploy_batch(count=6, cpu_per_container=250, memory_per_container=384)
    simulation_running = True
    simulation_task = asyncio.create_task(simulation_loop(tick_interval))
    return {"status": "started", "tick_interval": tick_interval}


@app.post("/api/simulation/stop")
async def stop_simulation():
    global simulation_running, simulation_task
    simulation_running = False
    if simulation_task:
        simulation_task.cancel()
        simulation_task = None
    return {"status": "stopped"}


@app.get("/api/simulation/status")
async def simulation_status():
    return {"running": simulation_running, "tick": get_cluster().tick_count}


@app.post("/api/pods/create")
async def create_pod(config: PodConfig):
    c = get_cluster()
    pod = c.create_pod(
        name=config.name,
        num_containers=config.num_containers,
        cpu_per_container=config.cpu_per_container,
        memory_per_container=config.memory_per_container,
        namespace=config.namespace,
        restart_policy=config.restart_policy,
    )
    return {"pod": pod.snapshot(), "state": c.snapshot()}


@app.post("/api/pods/batch")
async def create_batch(config: BatchConfig):
    c = get_cluster()
    pods = c.deploy_batch(
        count=config.count,
        cpu_per_container=config.cpu_per_container,
        memory_per_container=config.memory_per_container,
        num_containers=config.num_containers,
    )
    return {"pods": [p.snapshot() for p in pods], "state": c.snapshot()}


@app.delete("/api/pods/{pod_id}")
async def delete_pod(pod_id: str):
    c = get_cluster()
    ok = c.delete_pod(pod_id)
    return {"deleted": ok, "state": c.snapshot()}


@app.get("/api/pods")
async def list_pods():
    return {"pods": [p.snapshot() for p in get_cluster().pods]}


@app.post("/api/nodes/add")
async def add_node(config: NodeConfig):
    c = get_cluster()
    node = c.add_node(
        name=config.name,
        cpu_capacity=config.cpu_capacity,
        memory_capacity=config.memory_capacity,
    )
    return {"node": node.snapshot(), "state": c.snapshot()}


@app.delete("/api/nodes/{node_id}")
async def remove_node(node_id: str):
    c = get_cluster()
    ok = c.remove_node(node_id)
    return {"removed": ok, "state": c.snapshot()}


@app.post("/api/nodes/{node_id}/cordon")
async def cordon_node(node_id: str):
    c = get_cluster()
    node = next((n for n in c.nodes if n.id == node_id), None)
    if not node:
        return {"error": "Node not found"}
    node.cordon()
    c.logger.info("API", f"Node {node.name} cordoned", node_id=node.id)
    return {"node": node.snapshot()}


@app.post("/api/nodes/{node_id}/uncordon")
async def uncordon_node(node_id: str):
    c = get_cluster()
    node = next((n for n in c.nodes if n.id == node_id), None)
    if not node:
        return {"error": "Node not found"}
    node.uncordon()
    c.logger.info("API", f"Node {node.name} uncordoned", node_id=node.id)
    return {"node": node.snapshot()}


@app.get("/api/nodes")
async def list_nodes():
    return {"nodes": [n.snapshot() for n in get_cluster().nodes]}


@app.post("/api/scheduler/strategy")
async def set_strategy(config: StrategyConfig):
    c = get_cluster()
    c.set_scheduler_strategy(config.strategy)
    return {"strategy": config.strategy}


@app.get("/api/events")
async def get_events(count: int = Query(default=100)):
    return {"events": get_cluster().logger.recent(count)}


@app.get("/api/metrics")
async def get_metrics():
    return {
        "latest": get_cluster().metrics.latest,
        "history": get_cluster().metrics.recent(60),
    }


# ── WebSocket ───────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    try:
        await ws.send_text(json.dumps({
            "type": "init",
            "state": get_cluster().snapshot(),
        }, default=str))
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg.get("action") == "tick":
                c = get_cluster()
                result = c.tick()
                await ws.send_text(json.dumps({
                    "type": "tick",
                    "data": result,
                    "state": c.snapshot(),
                }, default=str))
    except WebSocketDisconnect:
        pass
    finally:
        if ws in connected_clients:
            connected_clients.remove(ws)
