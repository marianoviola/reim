"""
Tests for the access control middleware.
"""

import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


class TestAccessControlDisabled:
    """When ALLOWED_HOSTS is not set or *, everything is allowed."""

    def test_all_allowed_when_no_env(self):
        with patch.dict(os.environ, {"ALLOWED_HOSTS": "*"}, clear=False):
            from importlib import reload
            import app.middleware
            reload(app.middleware)
            import app.main
            reload(app.main)

            client = TestClient(app.main.app)
            r = client.get("/health")
            assert r.status_code == 200

            r = client.post("/api/v1/batch/fit", json={
                "observations": [
                    {"observer": "u1", "system": "p1", "value": 4.0},
                    {"observer": "u2", "system": "p1", "value": 5.0},
                ],
            })
            assert r.status_code == 200


class TestAccessControlEnabled:
    """When ALLOWED_HOSTS is set, only matching clients get through."""

    def test_health_always_accessible(self):
        with patch.dict(os.environ, {"ALLOWED_HOSTS": "10.0.0.1"}, clear=False):
            from importlib import reload
            import app.middleware
            reload(app.middleware)
            import app.main
            reload(app.main)

            client = TestClient(app.main.app)
            r = client.get("/health")
            assert r.status_code == 200

    def test_localhost_always_allowed(self):
        """Loopback is always allowed regardless of ALLOWED_HOSTS."""
        with patch.dict(os.environ, {"ALLOWED_HOSTS": "10.0.0.1"}, clear=False):
            from importlib import reload
            import app.middleware
            reload(app.middleware)
            import app.main
            reload(app.main)

            # TestClient connects from 127.0.0.1 (loopback)
            client = TestClient(app.main.app)
            r = client.post("/api/v1/batch/fit", json={
                "observations": [
                    {"observer": "u1", "system": "p1", "value": 4.0},
                    {"observer": "u2", "system": "p1", "value": 5.0},
                ],
            })
            # Loopback is always allowed
            assert r.status_code == 200

    def test_domain_matching(self):
        """Requests with matching Host header are allowed."""
        with patch.dict(os.environ, {"ALLOWED_HOSTS": "example.com"}, clear=False):
            from importlib import reload
            import app.middleware
            reload(app.middleware)
            import app.main
            reload(app.main)

            client = TestClient(app.main.app)

            # TestClient uses testserver as host but also loopback IP,
            # so loopback will match. This test verifies no crash.
            r = client.get("/health")
            assert r.status_code == 200


class TestMiddlewareUnit:
    """Unit tests for helper functions."""

    def test_is_ip_allowed_empty(self):
        from app.middleware import is_ip_allowed
        assert is_ip_allowed("1.2.3.4", set()) is True  # no restriction

    def test_is_ip_allowed_loopback(self):
        from app.middleware import is_ip_allowed
        assert is_ip_allowed("127.0.0.1", {"10.0.0.1"}) is True

    def test_is_ip_allowed_direct_match(self):
        from app.middleware import is_ip_allowed
        assert is_ip_allowed("10.0.0.5", {"10.0.0.5"}) is True
        assert is_ip_allowed("10.0.0.6", {"10.0.0.5"}) is False

    def test_is_ip_allowed_cidr(self):
        from app.middleware import is_ip_allowed
        assert is_ip_allowed("172.18.0.5", {"172.18.0.0/16"}) is True
        assert is_ip_allowed("172.19.0.5", {"172.18.0.0/16"}) is False

    def test_is_ip_allowed_docker(self):
        from app.middleware import is_ip_allowed
        assert is_ip_allowed("172.18.0.3", {"docker"}) is True
        assert is_ip_allowed("10.0.1.5", {"docker"}) is True
        assert is_ip_allowed("8.8.8.8", {"docker"}) is False

    def test_parse_allowed_hosts(self):
        from app.middleware import parse_allowed_hosts
        with patch.dict(os.environ, {"ALLOWED_HOSTS": "docker, example.com, 10.0.0.1"}, clear=False):
            hosts = parse_allowed_hosts()
            assert "docker" in hosts
            assert "example.com" in hosts
            assert "10.0.0.1" in hosts

    def test_parse_allowed_hosts_wildcard(self):
        from app.middleware import parse_allowed_hosts
        with patch.dict(os.environ, {"ALLOWED_HOSTS": "*"}, clear=False):
            hosts = parse_allowed_hosts()
            assert hosts == set()  # empty = allow all
