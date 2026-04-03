"""
Access control middleware for the REIM microservice.

Restricts access to allowed IPs, Docker network peers, and allowed domains.
The /health endpoint is always accessible (for Docker healthchecks and monitoring).
"""

import os
import re
import socket
import logging
import ipaddress
from typing import Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("reim-service")

# Paths that bypass access control (healthchecks, monitoring)
PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


def parse_allowed_hosts() -> Set[str]:
    """
    Parse ALLOWED_HOSTS env var into a set of allowed IPs and CIDR ranges.

    ALLOWED_HOSTS can contain:
    - IP addresses: 192.168.1.10
    - CIDR ranges: 172.18.0.0/16
    - Hostnames: myapp (resolved to IP at request time)
    - Domains: example.com (checked against Host header)
    - Special values: "docker" (allows Docker bridge networks 172.16.0.0/12)
    """
    raw = os.getenv("ALLOWED_HOSTS", "")
    if not raw or raw.strip() == "*":
        return set()  # empty = allow all (dev mode)

    return {h.strip() for h in raw.split(",") if h.strip()}


def is_ip_allowed(client_ip: str, allowed_hosts: Set[str]) -> bool:
    """Check if a client IP is in the allowed set."""
    if not allowed_hosts:
        return True  # no restriction configured

    try:
        client_addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False

    # Always allow loopback
    if client_addr.is_loopback:
        return True

    for host in allowed_hosts:
        # Check "docker" shorthand — allows all Docker bridge networks
        if host == "docker":
            docker_networks = [
                ipaddress.ip_network("172.16.0.0/12"),   # Docker default bridge range
                ipaddress.ip_network("10.0.0.0/8"),       # Common Docker overlay
                ipaddress.ip_network("192.168.0.0/16"),   # Docker compose networks
            ]
            if any(client_addr in net for net in docker_networks):
                return True
            continue

        # Check CIDR range
        if "/" in host:
            try:
                if client_addr in ipaddress.ip_network(host, strict=False):
                    return True
            except ValueError:
                pass
            continue

        # Check direct IP match
        try:
            if client_addr == ipaddress.ip_address(host):
                return True
            continue
        except ValueError:
            pass

        # It's a hostname — try to resolve it
        try:
            resolved_ips = socket.getaddrinfo(host, None)
            resolved = {info[4][0] for info in resolved_ips}
            if client_ip in resolved:
                return True
        except socket.gaierror:
            pass

    return False


def is_domain_allowed(request: Request, allowed_hosts: Set[str]) -> bool:
    """Check if the request's Host header or Origin matches an allowed domain."""
    if not allowed_hosts:
        return True

    host_header = request.headers.get("host", "")
    origin_header = request.headers.get("origin", "")

    # Extract domain (strip port)
    request_host = re.sub(r":\d+$", "", host_header).lower()
    origin_host = re.sub(r"https?://", "", origin_header).lower()
    origin_host = re.sub(r":\d+$", "", origin_host)

    for allowed in allowed_hosts:
        # Skip non-domain entries
        if "/" in allowed or allowed == "docker":
            continue

        # Skip IP addresses
        try:
            ipaddress.ip_address(allowed)
            continue
        except ValueError:
            pass

        # Domain match (exact or subdomain)
        allowed_lower = allowed.lower()
        if request_host == allowed_lower or request_host.endswith(f".{allowed_lower}"):
            return True
        if origin_host == allowed_lower or origin_host.endswith(f".{allowed_lower}"):
            return True

    return False


class AccessControlMiddleware(BaseHTTPMiddleware):
    """
    Middleware that restricts access to the REIM service.

    Configuration via ALLOWED_HOSTS environment variable:
      - Not set or "*"  → allow all (development mode)
      - "docker"        → allow Docker internal networks
      - IPs/CIDRs       → allow specific addresses
      - Hostnames        → resolved and matched against client IP
      - Domains          → matched against Host/Origin headers

    Examples:
      ALLOWED_HOSTS=docker                              # Docker only
      ALLOWED_HOSTS=docker,example.com                  # Docker + domain
      ALLOWED_HOSTS=172.18.0.0/16,93.184.216.34         # Specific network + IP
      ALLOWED_HOSTS=myapp,example.com                   # Container name + domain
    """

    def __init__(self, app):
        super().__init__(app)
        self.allowed_hosts = parse_allowed_hosts()
        if self.allowed_hosts:
            logger.info("Access control ENABLED. Allowed hosts: %s", self.allowed_hosts)
        else:
            logger.warning("Access control DISABLED (ALLOWED_HOSTS not set or '*'). All connections accepted.")

    async def dispatch(self, request: Request, call_next):
        # Public paths are always accessible
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # If no restrictions configured, allow all
        if not self.allowed_hosts:
            return await call_next(request)

        # Get client IP (handle proxies via X-Forwarded-For)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "0.0.0.0"

        # Check IP-based access
        if is_ip_allowed(client_ip, self.allowed_hosts):
            return await call_next(request)

        # Check domain-based access
        if is_domain_allowed(request, self.allowed_hosts):
            return await call_next(request)

        # Denied
        logger.warning(
            "Access DENIED: client_ip=%s, host=%s, path=%s",
            client_ip,
            request.headers.get("host", ""),
            request.url.path,
        )

        return JSONResponse(
            status_code=403,
            content={"detail": "Access denied. This service is restricted to authorized hosts."},
        )
