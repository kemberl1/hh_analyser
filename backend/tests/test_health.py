"""Tests for the health endpoint."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_root_health(client):
    """GET /health returns 200 with status ok."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_api_v1_health(client):
    """GET /api/v1/health returns 200 with status ok."""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    # db field may be 'unavailable' in tests (no real DB)
    assert "db" in data
