# Mini Container Orchestration Simulator

A from-scratch Kubernetes-style container orchestration engine that **schedules pods**, **allocates CPU/memory**, **handles node failures**, and visualizes everything through a **real-time web dashboard** and **CLI**.

Built to demonstrate deep understanding of how container orchestrators work under the hood.

---

## Dashboard

![Dashboard Screenshot](screenshots/dashboard.png)

*Real-time dashboard showing 3 cluster nodes, 11 running pods, CPU/memory utilization, container restarts, and a live event log — all updating via WebSocket.*

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        API Server (FastAPI)                     │
│              REST endpoints + WebSocket real-time               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────────┐  │
│  │   Scheduler   │   │   Cluster    │   │   Health Monitor   │  │
│  │              │   │   Manager    │   │                    │  │
│  │ ● First Fit  │   │              │   │ ● Failure detect   │  │
│  │ ● Best Fit   │◄─►│ ● Node mgmt  │◄─►│ ● Auto-eviction   │  │
│  │ ● Round Robin│   │ ● Pod CRUD   │   │ ● Auto-recovery   │  │
│  │ ● Least Load │   │ ● Tick engine│   │ ● Re-scheduling   │  │
│  └──────────────┘   └──────────────┘   └────────────────────┘  │
│           │                │                     │              │
│  ┌────────▼─────────────────▼─────────────────────▼──────────┐  │
│  │                    Core Models                            │  │
│  │  Node (CPU/MEM pool)  ←→  Pod (container group)          │  │
│  │  ResourcePool         ←→  Container (lifecycle)          │  │
│  └───────────────────────────────────────────────────────────┘  │
│           │                                                     │
│  ┌────────▼──────────────────────────────────────────────────┐  │
│  │              Monitoring & Observability                    │  │
│  │  EventLogger (structured events)                          │  │
│  │  MetricsCollector (CPU/MEM utilization history)           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                  Web Dashboard (single-page)                    │
│        Real-time via WebSocket · Nodes · Pods · Metrics         │
└─────────────────────────────────────────────────────────────────┘
```

## Key Features

### Scheduling Engine
- **4 pluggable strategies** — First Fit, Best Fit, Round Robin, Least Loaded
- Mirrors kube-scheduler's **filter → score → bind** cycle
- Pending queue with automatic retry for unschedulable pods
- Hot-swappable strategies at runtime

### Resource Management
- Per-node CPU (millicores) and memory (MB) tracking
- Allocation/release accounting with audit trail
- Utilization metrics (per-node and cluster-wide)

### Failure Handling
- **Node failures** — random crash simulation with configurable failure rates
- **Container failures** — individual containers crash independently
- **Auto-eviction** — pods on failed nodes are evicted and re-queued
- **Auto-recovery** — nodes heal after a cooldown, enabling rescheduling
- **Restart policies** — `Always` (auto-restart) and `Never` (fail permanently)

### Monitoring & Observability
- **Event log** — every scheduling decision, failure, and recovery is recorded
- **Metrics history** — CPU/memory utilization tracked over time
- **Real-time dashboard** — WebSocket-powered live updates

### Web Dashboard
- Cluster-wide stats (nodes, pods, CPU, memory, restarts, events)
- Per-node resource bars with color-coded utilization
- Pod table with status, resources, and delete actions
- CPU/memory utilization sparkline charts
- Structured event log with severity filtering
- Cordon/uncordon node controls
- Strategy switching at runtime

---

## Quick Start

### Prerequisites
- Python 3.10+

### Install

```bash
cd "Kubernetes Container Project"
pip install -r requirements.txt
```

### Run the Web Dashboard

```bash
python main.py server
```

Open **http://localhost:8000** — you'll see the orchestrator dashboard.

- Click **Start** to begin the simulation loop
- Click **+ Pod** or **+ Batch (5)** to deploy workloads
- Watch pods get scheduled, nodes fill up, failures happen, and recovery kick in
- Switch scheduling strategies live from the dropdown
- Click **Cordon** on a node to mark it unschedulable
- Click **Reset** to reinitialize the cluster

### Run the CLI Demo

```bash
python main.py demo
```

Runs 30 ticks of simulation in the terminal with a rich table view (if `rich` is installed) or plain text output.

### Run Tests

```bash
pytest tests/ -v
```

---

## Project Structure

```
├── main.py                     # Entry point (server / demo)
├── requirements.txt            # Python dependencies
├── README.md
├── src/
│   ├── cluster/
│   │   ├── node.py             # Node model — worker machine simulation
│   │   ├── cluster.py          # ClusterManager — central orchestration engine
│   │   └── resources.py        # ResourcePool — CPU/memory allocation tracking
│   ├── scheduler/
│   │   ├── scheduler.py        # Scheduler — pending queue + bind workflow
│   │   └── strategies.py       # Pluggable strategies (4 algorithms)
│   ├── pods/
│   │   ├── pod.py              # Pod model — container group with lifecycle
│   │   └── container.py        # Container model — individual process sim
│   ├── monitoring/
│   │   ├── health.py           # HealthMonitor — failure detection + recovery
│   │   ├── metrics.py          # MetricsCollector — utilization snapshots
│   │   └── logger.py           # EventLogger — structured cluster events
│   ├── api/
│   │   └── server.py           # FastAPI REST + WebSocket server
│   └── dashboard/
│       └── index.html          # Single-page real-time web dashboard
└── tests/
    ├── test_resources.py       # Resource allocation tests
    ├── test_scheduler.py       # Scheduler strategy tests
    ├── test_cluster.py         # Cluster integration tests
    └── test_pods.py            # Pod/Container lifecycle tests
```

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/cluster/init` | Initialize cluster with config |
| `GET` | `/api/cluster/state` | Full cluster snapshot |
| `POST` | `/api/cluster/tick` | Manual simulation tick |
| `POST` | `/api/simulation/start` | Start auto-simulation loop |
| `POST` | `/api/simulation/stop` | Stop simulation |
| `POST` | `/api/pods/create` | Create a single pod |
| `POST` | `/api/pods/batch` | Deploy multiple pods |
| `DELETE` | `/api/pods/{id}` | Delete a pod |
| `POST` | `/api/nodes/add` | Add a worker node |
| `DELETE` | `/api/nodes/{id}` | Remove a node (evicts pods) |
| `POST` | `/api/nodes/{id}/cordon` | Mark node unschedulable |
| `POST` | `/api/nodes/{id}/uncordon` | Mark node schedulable |
| `POST` | `/api/scheduler/strategy` | Change scheduling algorithm |
| `GET` | `/api/events` | Fetch event log |
| `GET` | `/api/metrics` | Fetch metrics history |
| `WS` | `/ws` | Real-time WebSocket feed |

## How It Maps to Real Kubernetes

| This Simulator | Real Kubernetes |
|----------------|-----------------|
| `ClusterManager` | kube-controller-manager |
| `Scheduler` + strategies | kube-scheduler (filter → score → bind) |
| `Node` + `ResourcePool` | kubelet + cAdvisor resource reporting |
| `Pod` / `Container` | Pod / Container specs & runtime |
| `HealthMonitor` | Node controller + pod eviction |
| `EventLogger` | Kubernetes Events (`kubectl get events`) |
| `MetricsCollector` | metrics-server / Prometheus |
| Dashboard | Kubernetes Dashboard / Lens |
| Cordon/Uncordon | `kubectl cordon/uncordon` |
| Restart policies | `restartPolicy: Always/Never` |

---

## Technologies

- **Python 3.10+** — core simulation engine
- **FastAPI** — async REST API + WebSocket server
- **Pydantic** — request validation
- **Rich** — terminal UI for CLI demo
- **HTML/CSS/JS** — zero-dependency dashboard (no build step)
- **pytest** — test suite

---

*Built as a portfolio project demonstrating container orchestration internals.*
