# REIM Service — Infrastructure & Deployment Guide

## Architecture

REIM runs on its own VPS. Communication with your application happens through a reverse proxy or Cloudflare Tunnel — no ports are exposed to the public internet.

```
┌──────────────┐     Reverse Proxy /      ┌──────────────┐
│  Your App    │     Cloudflare Tunnel     │ REIM VPS     │
│  VPS         │ ◄──────────────────────── │ FastAPI :8000│
│              │                           │ localhost    │
└──────────────┘                           └──────────────┘
```

**Why this setup:**

- REIM's port 8000 is never exposed to the internet
- If either IP changes, nothing breaks (tunnel is identity-based, not IP-based)
- Access control is enforced at both application and network levels

## VPS Specification

| | REIM VPS |
|---|---|
| **Provider** | Hetzner Cloud (or similar) |
| **Plan** | CX22 |
| **CPU** | 2 vCPU AMD |
| **RAM** | 4 GB |
| **Storage** | 40 GB SSD |
| **OS** | Ubuntu 24.04 LTS |
| **Cost** | ~€4.50/month |

## Initial Setup

### 1. Create the VPS

In your cloud provider's console:
- Create server: Ubuntu 24.04, 2 vCPU, 4GB RAM
- Add your SSH key
- Note the IP address

### 2. Provision

```bash
scp infrastructure/provision.sh root@<VPS_IP>:/root/
ssh root@<VPS_IP> 'chmod +x /root/provision.sh && /root/provision.sh'
```

### 3. Clone and first deploy

```bash
ssh deploy@<VPS_IP>
cd /opt/reim
git clone git@github.com:<your-org>/reim-service.git .
./deploy.sh
```

Verify locally:

```bash
ssh deploy@<VPS_IP> 'curl -s http://localhost:8000/health'
# → {"status":"healthy","version":"1.0.0","models_loaded":0}
```

## Cloudflare Tunnel Setup (Optional)

If you want to expose REIM via Cloudflare Tunnel instead of a traditional reverse proxy:

### Step 1: Authenticate cloudflared

```bash
ssh deploy@<VPS_IP>
cloudflared tunnel login
```

### Step 2: Create the tunnel

```bash
cloudflared tunnel create reim
```

### Step 3: Configure

```bash
sudo tee /etc/cloudflared/config.yml << EOF
tunnel: <TUNNEL_ID>
credentials-file: /home/deploy/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: reim.yourdomain.com
    service: http://localhost:8000
    originRequest:
      noTLSVerify: true
  - service: http_status:404
EOF
```

### Step 4: DNS record

```bash
cloudflared tunnel route dns reim reim.yourdomain.com
```

### Step 5: Run as a system service

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

## Cloudflare Access — Restrict Access (Optional)

Use Cloudflare Access (Zero Trust) to restrict who can reach the REIM API:

1. Go to **Zero Trust → Access → Applications → Add Self-hosted**
2. Domain: `reim.yourdomain.com`
3. Create a **Service Token** for your application
4. Configure your app to send `CF-Access-Client-Id` and `CF-Access-Client-Secret` headers

### Bypass for health endpoint

Add a Bypass policy for path `/health` to allow monitoring without authentication.

## GitHub Actions — Automatic Deploy

### Secrets required

| Secret | Value |
|--------|-------|
| `VPS_HOST` | REIM VPS IP address |
| `VPS_USER` | `deploy` |
| `VPS_SSH_KEY` | Private SSH key for deploy user |

### Flow

```
Push to main → Run tests (GitHub) → SSH to VPS → git pull + docker compose up
```

### Manual deploy

```bash
ssh deploy@<VPS_IP>
cd /opt/reim
./deploy.sh
```

## Service Resilience

### What happens if REIM goes down?

**Your application keeps working.** REIM should never be in the critical path:

1. Scores are pre-calculated by a nightly batch job and stored in your database. If REIM is unavailable, the last scores remain valid.
2. Your REIM client should catch all exceptions. If REIM doesn't respond, fall back to simple averages.
3. Online REIM state is ephemeral — lost on container restart. The nightly batch recalibrates everything.

### Auto-restart

Docker's `restart: unless-stopped` handles crashes. If using Cloudflare Tunnel, the `cloudflared` daemon also auto-restarts via systemd.

### Monitoring

- Point an uptime monitor at `https://reim.yourdomain.com/health`
- Self-heal cron: `*/5 * * * * deploy curl -sf http://localhost:8000/health > /dev/null || (cd /opt/reim && docker compose restart reim-api)`

## Manual Operations

```bash
ssh deploy@<VPS_IP>
cd /opt/reim

# Logs
docker compose logs -f reim-api

# Restart
docker compose restart reim-api

# Resource usage
docker stats reim-service

# Update .env
nano .env && docker compose down && docker compose up -d
```

## Cost Summary

| Item | Monthly Cost |
|---|---|
| Hetzner CX22 (or equivalent) | ~€4.50 |
| Cloudflare Tunnel | Free |
| Cloudflare Access (50 users) | Free |
| **Total** | **~€4.50/month** |
