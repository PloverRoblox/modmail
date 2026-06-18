#!/usr/bin/env bash
#
# One-time host setup for running Modmail on an Oracle Cloud VM.
# Installs Docker + Compose and opens the logviewer port (8000) on the instance
# firewall. Works on Ubuntu (apt) and Oracle Linux (dnf) images.
#
# Usage (run on the VM):
#   chmod +x setup.sh && ./setup.sh
#
# NOTE: This handles the *instance* firewall only. You must ALSO open port 8000
# (and 22 for SSH) in the OCI Console -> VCN -> Security List. See README.md.

set -euo pipefail

LOGVIEWER_PORT=8000
SWAP_SIZE=2G

echo "==> Ensuring swap exists (important on 1 GB shapes like E2.1.Micro)..."
if ! sudo swapon --show | grep -q '/swapfile'; then
    sudo fallocate -l "${SWAP_SIZE}" /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
else
    echo "    Swap already present, skipping."
fi

echo "==> Installing Docker Engine + Compose plugin..."
if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh
fi

echo "==> Adding current user to the docker group (re-login to take effect)..."
sudo usermod -aG docker "$USER" || true

echo "==> Enabling and starting Docker..."
sudo systemctl enable --now docker

echo "==> Opening instance firewall on port ${LOGVIEWER_PORT}..."
if command -v firewall-cmd >/dev/null 2>&1; then
    # Oracle Linux ships firewalld.
    sudo firewall-cmd --permanent --add-port=${LOGVIEWER_PORT}/tcp
    sudo firewall-cmd --reload
elif command -v iptables >/dev/null 2>&1; then
    # Ubuntu Oracle images ship a restrictive iptables ruleset.
    sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport ${LOGVIEWER_PORT} -j ACCEPT
    if command -v netfilter-persistent >/dev/null 2>&1; then
        sudo netfilter-persistent save
    else
        echo "    (Install iptables-persistent to make this rule survive reboot.)"
    fi
fi

echo ""
echo "==> Host setup complete."
echo "    1. Log out and back in (so the docker group applies)."
echo "    2. cp .env.example .env  &&  edit .env with your values."
echo "    3. docker compose up -d --build"
echo "    4. Make sure port ${LOGVIEWER_PORT} is also open in the OCI Security List."
