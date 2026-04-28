#!/bin/bash
wget -q -O /usr/local/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x /usr/local/bin/cloudflared
echo "cloudflared installed"
cloudflared tunnel --url http://localhost:8099
