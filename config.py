"""Конфигурация Trigger Tracker"""
import os
from dotenv import load_dotenv
load_dotenv()

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

# Re-export for web.py
BOT_TOKEN = os.environ.get("TRACKER_BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("TRACKER_OWNER_ID", "0"))

# Apple Calendar (.ics URL)
ICAL_URL = os.environ.get("ICAL_URL", "")
