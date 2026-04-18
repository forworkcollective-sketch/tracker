"""
Запуск Trigger Tracker: бот + веб одновременно
"""
import threading
import uvicorn
from config import WEB_HOST, WEB_PORT

def run_web():
    """Запуск веб-дашборда в отдельном потоке"""
    uvicorn.run("web:app", host=WEB_HOST, port=WEB_PORT, log_level="warning")

def run_bot():
    """Запуск Telegram бота"""
    from bot import main
    main()

if __name__ == "__main__":
    print("🚀 Trigger Tracker запускается...")
    print(f"🌐 Дашборд: http://localhost:{WEB_PORT}")
    print("🤖 Telegram бот: запуск...")
    print()

    # Web в фоновом потоке
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()

    # Бот в основном потоке
    run_bot()
