#!/bin/bash
# ========================================================
# Restream IPTV Suite - Auto Installer for Ubuntu / Debian
# ========================================================

set -e

PORT=8080
INSTALL_DIR=$(pwd)
CURRENT_USER=$(whoami)

echo "========================================================"
echo "    Installing Restream IPTV Suite on Ubuntu / Debian   "
echo "========================================================"
echo "Installation directory: $INSTALL_DIR"
echo "Port: $PORT"
echo ""

# 1. Update system packages and install prerequisites
echo "[1/5] Updating packages and installing Python3 & FFmpeg..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip ffmpeg curl ufw

# 2. Allow firewall port if UFW is active
echo "[2/5] Configuring firewall port $PORT..."
if sudo ufw status | grep -q "Status: active"; then
    sudo ufw allow $PORT/tcp
    echo "Port $PORT opened in UFW firewall."
fi

# 3. Create systemd 24/7 background service
echo "[3/5] Creating systemd service (restream.service)..."
SERVICE_FILE="/etc/systemd/system/restream.service"

sudo bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=Restream IPTV Proxy Server
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/run_server.py --port $PORT
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF"

# 4. Enable and start the service
echo "[4/5] Reloading systemd and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable restream.service
sudo systemctl restart restream.service

# 5. Detect server IP
SERVER_IP=$(curl -s -4 ifconfig.me || hostname -I | awk '{print $1}')

echo ""
echo "========================================================"
echo "         Installation Complete & Service Started!       "
echo "========================================================"
echo "Status: Running in background 24/7 via systemd"
echo ""
echo "Web Player:       http://${SERVER_IP}:${PORT}"
echo "M3U Playlist:     http://${SERVER_IP}:${PORT}/playlist.m3u"
echo "Sports Only M3U:  http://${SERVER_IP}:${PORT}/playlist.m3u?group=Sports"
echo ""
echo "Useful Commands:"
echo " - View logs:       sudo journalctl -u restream -f"
echo " - Restart server:  sudo systemctl restart restream"
echo " - Stop server:     sudo systemctl stop restream"
echo " - Status:          sudo systemctl status restream"
echo "========================================================"
