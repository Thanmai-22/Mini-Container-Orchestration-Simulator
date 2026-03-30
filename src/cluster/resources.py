"""Resource management for the cluster — tracks CPU and memory allocation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ResourceRequest:
    """Specifies how much CPU (millicores) and memory (MB) a workload needs."""
    cpu_millicores: int = 100
    memory_mb: int = 128

    def fits_within(self, pool: ResourcePool) -> bool:
        return (
            self.cpu_millicores <= pool.available_cpu
            and self.memory_mb <= pool.available_memory
        )


@dataclass
class ResourcePool:
    """Tracks total and allocated resources on a single node."""
    total_cpu: int          # millicores
    total_memory: int       # MB
    allocated_cpu: int = 0
    allocated_memory: int = 0
    _allocation_log: list[dict] = field(default_factory=list, repr=False)

    @property
    def available_cpu(self) -> int:
        return self.total_cpu - self.allocated_cpu

    @property
    def available_memory(self) -> int:
        return self.total_memory - self.allocated_memory

    @property
    def cpu_utilization(self) -> float:
        if self.total_cpu == 0:
            return 0.0
        return self.allocated_cpu / self.total_cpu

    @property
    def memory_utilization(self) -> float:
        if self.total_memory == 0:
            return 0.0
        return self.allocated_memory / self.total_memory

    @property
    def overall_utilization(self) -> float:
        return (self.cpu_utilization + self.memory_utilization) / 2

    def allocate(self, request: ResourceRequest, owner_id: str) -> bool:
        if not request.fits_within(self):
            return False
        self.allocated_cpu += request.cpu_millicores
        self.allocated_memory += request.memory_mb
        self._allocation_log.append({
            "action": "allocate",
            "owner": owner_id,
            "cpu": request.cpu_millicores,
            "memory": request.memory_mb,
        })
        return True

    def release(self, request: ResourceRequest, owner_id: str) -> None:
        self.allocated_cpu = max(0, self.allocated_cpu - request.cpu_millicores)
        self.allocated_memory = max(0, self.allocated_memory - request.memory_mb)
        self._allocation_log.append({
            "action": "release",
            "owner": owner_id,
            "cpu": request.cpu_millicores,
            "memory": request.memory_mb,
        })

    def snapshot(self) -> dict:
        return {
            "total_cpu": self.total_cpu,
            "total_memory": self.total_memory,
            "allocated_cpu": self.allocated_cpu,
            "allocated_memory": self.allocated_memory,
            "available_cpu": self.available_cpu,
            "available_memory": self.available_memory,
            "cpu_utilization": round(self.cpu_utilization * 100, 1),
            "memory_utilization": round(self.memory_utilization * 100, 1),
        }
