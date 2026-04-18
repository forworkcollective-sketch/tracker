#!/bin/bash
# ===========================================
# Деплой Trigger Tracker на Timeweb VPS
# Запусти: bash deploy.sh
# ===========================================

set -e

# ---- НАСТРОЙКИ (заполни перед запуском) ----
VPS_IP="YOUR_VPS_IP"
VPS_USER="YOUR_USER"
REMOTE_DIR="/opt/tracker"
SERVICE_NAME="tracker"
# --------------------------------------------

# Проверка что настройки заполнены
if [[ "$VPS_IP" == "YOUR_VPS_IP" || "$VPS_USER" == "YOUR_USER" ]]; then
    echo "Заполни VPS_IP и VPS_USER в начале deploy.sh"
    exit 1
fi

SSH_TARGET="${VPS_USER}@${VPS_IP}"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Deploying Trigger Tracker to ${SSH_TARGET}..."
echo ""

# --- 1. Копируем файлы на VPS ---
echo "[1/5] Копирую файлы на VPS..."
rsync -avz --delete \
    --exclude 'venv/' \
    --exclude '__pycache__/' \
    --exclude '.env' \
    --exclude '*.pyc' \
    --exclude '.git/' \
    "$LOCAL_DIR/" "${SSH_TARGET}:${REMOTE_DIR}/"

# --- 2. Копируем .env ---
echo "[2/5] Копирую .env..."
if [ -f "$LOCAL_DIR/.env" ]; then
    scp "$LOCAL_DIR/.env" "${SSH_TARGET}:${REMOTE_DIR}/.env"
else
    echo "  .env не найден локально, пропускаю"
fi

# --- 3. Устанавливаем зависимости в venv на VPS ---
echo "[3/5] Создаю venv и ставлю зависимости..."
ssh "$SSH_TARGET" bash -s <<REMOTE
set -e
cd ${REMOTE_DIR}

# Создаём venv если нет
if [ ! -d venv ]; then
    python3.11 -m venv venv || python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "  Зависимости установлены"
REMOTE

# --- 4. Устанавливаем systemd сервис ---
echo "[4/5] Настраиваю systemd сервис..."
ssh "$SSH_TARGET" bash -s <<REMOTE
set -e

# Подставляем юзера в service-файл и копируем
sed "s/YOUR_USER/${VPS_USER}/g" ${REMOTE_DIR}/tracker.service | sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
echo "  Сервис зарегистрирован"
REMOTE

# --- 5. Перезапускаем сервис ---
echo "[5/5] Перезапускаю сервис..."
ssh "$SSH_TARGET" "sudo systemctl restart ${SERVICE_NAME}"

echo ""
echo "Done! Trigger Tracker запущен на ${VPS_IP}"
echo ""
echo "  Дашборд:  http://${VPS_IP}:8099"
echo "  Статус:   ssh ${SSH_TARGET} 'sudo systemctl status ${SERVICE_NAME}'"
echo "  Логи:     ssh ${SSH_TARGET} 'journalctl -u ${SERVICE_NAME} -f'"
