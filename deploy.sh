#!/bin/bash
set -e

echo "=== TRACKER DEPLOY ==="

# 1. System packages
apt update && apt install -y python3 python3-venv python3-pip nginx git

# 2. Clone repo
rm -rf /opt/tracker
git clone https://github.com/forworkcollective-sketch/tracker.git /opt/tracker
cd /opt/tracker

# 3. Create .env
cat > /opt/tracker/.env << 'ENVEOF'
TRACKER_BOT_TOKEN=8395295166:AAGSH2UnkwFr4QxjJseW0sh7HX8WpguuqcM
TRACKER_OWNER_ID=584623208
SUPABASE_URL=https://hwdnbfzbnwutqctqqdpm.supabase.co
SUPABASE_KEY=sb_secret_IOexrj1UyBsv6tjr5VlZ_g_AC4PDciR
WEB_PORT=8099
ENVEOF

# 4. Python venv + deps
python3 -m venv /opt/tracker/venv
/opt/tracker/venv/bin/pip install --upgrade pip
/opt/tracker/venv/bin/pip install -r /opt/tracker/requirements.txt
/opt/tracker/venv/bin/pip install python-dotenv

# 5. Systemd service
cat > /etc/systemd/system/tracker.service << 'SVCEOF'
[Unit]
Description=Trigger Tracker Bot + Web
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/tracker
EnvironmentFile=/opt/tracker/.env
ExecStart=/opt/tracker/venv/bin/python run.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tracker

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable tracker
systemctl start tracker

# 6. Nginx reverse proxy
cat > /etc/nginx/sites-available/tracker << 'NGXEOF'
server {
    listen 80;
    server_name 72.56.5.173;

    location / {
        proxy_pass http://127.0.0.1:8099;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGXEOF

ln -sf /etc/nginx/sites-available/tracker /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo "=== DEPLOY DONE ==="
echo "Web: http://72.56.5.173"
echo "Check: systemctl status tracker"
