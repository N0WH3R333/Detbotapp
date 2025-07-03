import os
from dotenv import load_dotenv

# Сначала загружаем основной .env файл (для совместимости)
load_dotenv()
# Затем пытаемся загрузить локальный .env.local.
# Если он существует, его переменные переопределят значения из .env
load_dotenv(dotenv_path=".env.local")

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL_HANDLERS = os.getenv("LOG_LEVEL_HANDLERS", "INFO").upper()
LOG_LEVEL_AIOGRAM = os.getenv("LOG_LEVEL_AIOGRAM", "INFO").upper()
LOG_LEVEL_DATABASE = os.getenv("LOG_LEVEL_DATABASE", "INFO").upper()
LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", 5 * 1024 * 1024))  # 5 MB
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", 5))

WEBAPP_URL = os.getenv("WEBAPP_URL")
DELIVERY_COST = int(os.getenv("DELIVERY_COST", 300))
REMINDER_HOURS_BEFORE = int(os.getenv("REMINDER_HOURS_BEFORE", 24))

DAILY_REPORT_TIME = os.getenv("DAILY_REPORT_TIME", "21:00")
WEEKLY_REPORT_DAY_OF_WEEK = os.getenv("WEEKLY_REPORT_DAY_OF_WEEK", "sun")
WEEKLY_REPORT_TIME = os.getenv("WEEKLY_REPORT_TIME", "22:00")
MAX_PARALLEL_BOOKINGS = int(os.getenv("MAX_PARALLEL_BOOKINGS", 12))

# Данные по товарам и промокодам теперь загружаются динамически из JSON-файлов
# через функции в database/db.py
