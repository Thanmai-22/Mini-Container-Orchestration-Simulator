"""Tests for resource pool allocation and tracking."""

import pytest
from src.cluster.resources import ResourcePool, ResourceRequest


def test_allocation_within_capacity():
    pool = ResourcePool(total_cpu=4000, total_memory=8192)
    req = ResourceRequest(cpu_millicores=1000, memory_mb=2048)
    assert pool.allocate(req, "pod-1") is True
    assert pool.allocated_cpu == 1000
    assert pool.allocated_memory == 2048
    assert pool.available_cpu == 3000


def test_allocation_exceeds_capacity():
    pool = ResourcePool(total_cpu=1000, total_memory=512)
    req = ResourceRequest(cpu_millicores=2000, memory_mb=256)
    assert pool.allocate(req, "pod-x") is False
    assert pool.allocated_cpu == 0


def test_release_restores_resources():
    pool = ResourcePool(total_cpu=4000, total_memory=8192)
    req = ResourceRequest(cpu_millicores=1000, memory_mb=2048)
    pool.allocate(req, "pod-1")
    pool.release(req, "pod-1")
    assert pool.available_cpu == 4000
    assert pool.available_memory == 8192


def test_utilization_calculation():
    pool = ResourcePool(total_cpu=2000, total_memory=4000)
    req = ResourceRequest(cpu_millicores=1000, memory_mb=2000)
    pool.allocate(req, "pod-1")
    assert pool.cpu_utilization == pytest.approx(0.5)
    assert pool.memory_utilization == pytest.approx(0.5)
    assert pool.overall_utilization == pytest.approx(0.5)


def test_fits_within():
    pool = ResourcePool(total_cpu=1000, total_memory=512)
    small = ResourceRequest(cpu_millicores=500, memory_mb=256)
    big = ResourceRequest(cpu_millicores=1500, memory_mb=256)
    assert small.fits_within(pool) is True
    assert big.fits_within(pool) is False
