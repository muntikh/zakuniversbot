#!/usr/bin/env bash
# ==============================================================================
# Zak Univers Telegram Bot - Automated 24/7 VPS Deployer (systemd)
# ==============================================================================
set -e

APP_DIR="/opt/zakuniversbot"
SERVICE_NAME="zakunivers"

echo "🚀 [1/5] Updating packages and installing prerequisites..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv git curl

echo "📦 [2/5] Setting up project directory at $APP_DIR..."
if [ -d "$APP_DIR/.git" ]; then
    echo "Updating existing repository..."
    cd "$APP_DIR"
    git fetch origin
    git reset --hard origin/main
else
    echo "Cloning repository..."
    sudo git clone https://github.com/muntikh/zakuniversbot.git "$APP_DIR"
    cd "$APP_DIR"
fi

sudo chown -R $USER:$USER "$APP_DIR"

echo "🐍 [3/5] Setting up Python virtual environment..."
if [ ! -d "$APP_DIR/.venv" ]; then
    python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "⚙️ [4/5] Checking .env configuration..."
if [ ! -f "$APP_DIR/.env" ]; then
    if [ -f "$APP_DIR/.env.example" ]; then
        echo "Creating .env from .env.example..."
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    else
        touch "$APP_DIR/.env"
    fi
    echo "⚠️ Please ensure $APP_DIR/.env contains your BOT_TOKEN and PANEL credentials."
fi

echo "🔄 [5/5] Creating systemd service ($SERVICE_NAME)..."
sudo bash -c "cat << 'EOF' > /etc/systemd/system/${SERVICE_NAME}.service
[Unit]
Description=Zak Univers Telegram Bot 24/7 Daemon
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python -m bot.main
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl restart ${SERVICE_NAME}

echo ""
echo "✅ ========================================================="
echo "✅ Zak Univers Bot successfully deployed and running 24/7!"
echo "✅ Check status: sudo systemctl status $SERVICE_NAME"
echo "✅ View live logs: sudo journalctl -u $SERVICE_NAME -f"
echo "✅ ========================================================="
