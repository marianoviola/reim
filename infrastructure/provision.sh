#!/bin/bash
# =============================================================================
# REIM Service — VPS Provisioning Script for Hetzner
# =============================================================================
#
# Target: Hetzner CX22 (2 vCPU AMD, 4GB RAM, 40GB SSD, 20TB traffic)
# OS: Ubuntu 24.04
# Cost: ~€4.50/month
#
# Architecture: REIM runs on its own VPS, separate from your application.
# Communication: via Cloudflare Tunnel (no ports exposed to internet).
#
# Usage:
#   scp infrastructure/provision.sh root@<VPS_IP>:/root/
#   ssh root@<VPS_IP> 'chmod +x /root/provision.sh && /root/provision.sh'
#
# =============================================================================

set -euo pipefail

DEPLOY_USER="deploy"
APP_DIR="/opt/reim"

echo "============================================================"
echo "  REIM Service — VPS Provisioning"
echo "============================================================"

# ---- 1. System updates ----
echo "[1/9] Updating system..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    curl wget git ufw fail2ban \
    unattended-upgrades apt-listchanges \
    ca-certificates gnupg lsb-release

cat > /etc/apt/apt.conf.d/20auto-upgrades << EOF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF

# ---- 2. Create deploy user ----
echo "[2/9] Creating deploy user..."
if ! id "$DEPLOY_USER" &>/dev/null; then
    useradd -m -s /bin/bash -G sudo "$DEPLOY_USER"
    echo "$DEPLOY_USER ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$DEPLOY_USER
    chmod 0440 /etc/sudoers.d/$DEPLOY_USER
    mkdir -p /home/$DEPLOY_USER/.ssh
    cp /root/.ssh/authorized_keys /home/$DEPLOY_USER/.ssh/
    chown -R $DEPLOY_USER:$DEPLOY_USER /home/$DEPLOY_USER/.ssh
    chmod 700 /home/$DEPLOY_USER/.ssh
    chmod 600 /home/$DEPLOY_USER/.ssh/authorized_keys
    echo "  → User '$DEPLOY_USER' created"
else
    echo "  → User '$DEPLOY_USER' already exists"
fi

# ---- 3. Generate GitHub deploy key ----
echo "[3/9] Generating GitHub deploy key..."
DEPLOY_KEY="/home/$DEPLOY_USER/.ssh/id_ed25519"
if [ ! -f "$DEPLOY_KEY" ]; then
    su - $DEPLOY_USER -c "ssh-keygen -t ed25519 -C 'reim-deploy' -f $DEPLOY_KEY -N ''"
    # Pre-accept github.com host key
    su - $DEPLOY_USER -c "ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts 2>/dev/null"
    echo "  → Deploy key generated"
else
    echo "  → Deploy key already exists"
fi

# ---- 4. Install Docker ----
echo "[4/9] Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker $DEPLOY_USER
    systemctl enable docker
    echo "  → Docker installed"
else
    echo "  → Docker already installed"
fi

# ---- 5. Install Cloudflare Tunnel (cloudflared) ----
echo "[5/9] Installing cloudflared..."
if ! command -v cloudflared &>/dev/null; then
    curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
        -o /usr/local/bin/cloudflared
    chmod +x /usr/local/bin/cloudflared
    echo "  → cloudflared installed"
else
    echo "  → cloudflared already installed"
fi

# ---- 6. Firewall ----
echo "[6/9] Configuring firewall..."
ufw --force reset > /dev/null 2>&1
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw --force enable
echo "  → Firewall: SSH only (REIM via Cloudflare Tunnel)"

# ---- 7. Fail2ban ----
echo "[7/9] Configuring fail2ban..."
cat > /etc/fail2ban/jail.local << EOF
[sshd]
enabled = true
port = ssh
maxretry = 5
bantime = 3600
findtime = 600
EOF
systemctl enable fail2ban
systemctl restart fail2ban

# ---- 8. Application directory + .env ----
echo "[8/9] Setting up application..."
mkdir -p $APP_DIR
chown $DEPLOY_USER:$DEPLOY_USER $APP_DIR

cat > $APP_DIR/.env << 'EOF'
# REIM Service — Production
PORT=8000
LOG_LEVEL=WARNING
MAX_ONLINE_INSTANCES=50
MAX_BATCH_OBSERVATIONS=1000000
ALLOWED_HOSTS=docker
CORS_ORIGINS=*
EOF

chown $DEPLOY_USER:$DEPLOY_USER $APP_DIR/.env
chmod 600 $APP_DIR/.env

# ---- 9. Clone repo and create deploy script ----
echo "[9/9] Initializing git repo..."
su - $DEPLOY_USER -c "cd $APP_DIR && git init" 2>/dev/null || true

cat > $APP_DIR/deploy.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail
cd /opt/reim

echo "→ Pulling latest code..."
git fetch origin main
git reset --hard origin/main

echo "→ Building and restarting..."
docker compose down
docker compose up --build -d

echo "→ Waiting for health check..."
for i in {1..10}; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "✓ REIM service is healthy"
        exit 0
    fi
    sleep 3
done

echo "✗ Health check failed!"
docker compose logs --tail 30
exit 1
SCRIPT

chmod +x $APP_DIR/deploy.sh
chown $DEPLOY_USER:$DEPLOY_USER $APP_DIR/deploy.sh

# ---- Done ----
VPS_IP=$(curl -s4 ifconfig.me)
PUBKEY=$(cat /home/$DEPLOY_USER/.ssh/id_ed25519.pub)

echo ""
echo "============================================================"
echo "  Provisioning complete!"
echo "============================================================"
echo ""
echo "  Server IP: $VPS_IP"
echo ""
echo "  ┌─────────────────────────────────────────────────────┐"
echo "  │  DEPLOY KEY (add to GitHub as Deploy Key):          │"
echo "  ├─────────────────────────────────────────────────────┤"
echo "  │  $PUBKEY"
echo "  └─────────────────────────────────────────────────────┘"
echo ""
echo "  Add this key to your Git repository as a Deploy Key"
echo ""
echo "  Then run (as deploy user):"
echo "     su - $DEPLOY_USER"
echo "     cd $APP_DIR"
echo "     git fetch origin main"
echo "     git checkout -b main origin/main"
echo "     ./deploy.sh"
echo ""
echo "  Cloudflare Tunnel setup:"
echo "     cloudflared tunnel login"
echo "     cloudflared tunnel create reim"
echo "     (see infrastructure/DEPLOYMENT.md)"
echo ""
echo "  GitHub Actions secrets:"
echo "     VPS_HOST = $VPS_IP"
echo "     VPS_USER = $DEPLOY_USER"
echo "     VPS_SSH_KEY = (contents of ~/.ssh/reim_deploy)"
echo "============================================================"
