#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/paios-ui.service"

if [ ! -f "$SERVICE_FILE" ]; then
  echo "Error: paios-ui.service not found in $SCRIPT_DIR"
  exit 1
fi

echo "Installing PAIOS UI service..."
echo "Make sure you've edited paios-ui.service with your username and paths first!"
echo ""

sudo cp "$SERVICE_FILE" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable paios-ui
sudo systemctl start paios-ui
sudo systemctl status paios-ui
