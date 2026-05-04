#!/usr/bin/env bash
# scripts/deploy.sh
# Manual deployment script - run on the Raspberry Pi via SSH.
set -euo pipefail

# Use ROCKET_DIR env var, or default to /opt/rocket, or use script's parent directory
ROCKET_DIR="${ROCKET_DIR:-/opt/rocket}"
VENV_DIR="${ROCKET_DIR}/venv"
DATA_DIR="${ROCKET_DIR}/data"

echo "=== Rocket Flight Computer - Deploy ==="

if [ ! -d "$ROCKET_DIR" ]; then
    echo "[0/5] Creating directory structure..."
    sudo mkdir -p "$ROCKET_DIR"
    sudo chown "$USER:$USER" "$ROCKET_DIR"
fi

cd "$ROCKET_DIR"
echo "[1/5] Pulling latest code..."
git pull

if [ ! -d "$VENV_DIR" ]; then
    echo "[2/5] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "[2/5] Virtual environment exists."
fi

echo "[3/5] Installing dependencies..."
"$VENV_DIR/bin/pip" install -r requirements.txt --quiet

mkdir -p "$DATA_DIR"

echo "[4/5] Updating systemd services..."
sudo cp config/rocket-flight.service /etc/systemd/system/
sudo cp config/rocket-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rocket-flight.service

echo "[5/5] Restarting services..."
sudo systemctl restart rocket-flight.service
sudo systemctl restart rocket-dashboard.service

echo ""
echo "=== Deploy complete ==="
echo "Flight Controller: $(sudo systemctl is-active rocket-flight.service)"
echo "Dashboard:         $(sudo systemctl is-active rocket-dashboard.service)"
echo "Dashboard URL:     http://$(hostname).local:8080"
