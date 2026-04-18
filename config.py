"""Конфигурация Trigger Tracker"""
import os

# Telegram
BOT_TOKEN = os.environ.get("TRACKER_BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("TRACKER_OWNER_ID", "0"))

# Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")  # service_role key

# Дневной бюджет в минутах
DAILY_BUDGET_MINUTES = 240  # 4 часа

# Web-сервер
WEB_HOST = "0.0.0.0"
WEB_PORT = int(os.environ.get("WEB_PORT", "8099"))
