import os
from dotenv import load_dotenv

# Сначала загружаем основной .env файл (для совместимости)
load_dotenv()
# Затем пытаемся загрузить локальный .env.local.
# Если он существует, его переменные переопределят значения из .env
load_dotenv(dotenv_path=".env.local")

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Поддержка нескольких администраторов. ID указываются в .env через запятую.
ADMIN_ID_STR = os.getenv("ADMIN_ID")
ADMIN_IDS = []
if ADMIN_ID_STR:
    try:
        ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_ID_STR.split(',')]
    except ValueError:
        print(f"ОШИБКА: Переменная ADMIN_ID в .env файле содержит нечисловые значения: '{ADMIN_ID_STR}'")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL_HANDLERS = os.getenv("LOG_LEVEL_HANDLERS", "INFO").upper()
LOG_LEVEL_AIOGRAM = os.getenv("LOG_LEVEL_AIOGRAM", "INFO").upper()
LOG_LEVEL_DATABASE = os.getenv("LOG_LEVEL_DATABASE", "INFO").upper()
LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_FILE = os.getenv("LOG_FILE", "bot.log") 

WEBAPP_URL = os.getenv("WEBAPP_URL")
try:
    LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", 5 * 1024 * 1024))  # 5 MB
except (ValueError, TypeError):
    LOG_MAX_BYTES = 5 * 1024 * 1024
    print(f"ОШИБКА: Переменная LOG_MAX_BYTES имеет неверный формат. Установлено значение по умолчанию: {LOG_MAX_BYTES}")

try:
    LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", 5))
except (ValueError, TypeError):
    LOG_BACKUP_COUNT = 5
    print(f"ОШИБКА: Переменная LOG_BACKUP_COUNT имеет неверный формат. Установлено значение по умолчанию: {LOG_BACKUP_COUNT}")

try:
    DELIVERY_COST = int(os.getenv("DELIVERY_COST", 300))
except (ValueError, TypeError):
    DELIVERY_COST = 300
    print(f"ОШИБКА: Переменная DELIVERY_COST имеет неверный формат. Установлено значение по умолчанию: {DELIVERY_COST}")

try:
    REMINDER_HOURS_BEFORE = int(os.getenv("REMINDER_HOURS_BEFORE", 3))
except (ValueError, TypeError):
    REMINDER_HOURS_BEFORE = 3
    print(f"ОШИБКА: Переменная REMINDER_HOURS_BEFORE имеет неверный формат. Установлено значение по умолчанию: {REMINDER_HOURS_BEFORE}")

DAILY_REPORT_TIME = os.getenv("DAILY_REPORT_TIME", "21:00")
WEEKLY_REPORT_DAY_OF_WEEK = os.getenv("WEEKLY_REPORT_DAY_OF_WEEK", "sun")
WEEKLY_REPORT_TIME = os.getenv("WEEKLY_REPORT_TIME", "22:00")
try:
    MAX_PARALLEL_BOOKINGS = int(os.getenv("MAX_PARALLEL_BOOKINGS", 12))
except (ValueError, TypeError):
    MAX_PARALLEL_BOOKINGS = 12
    print(f"ОШИБКА: Переменная MAX_PARALLEL_BOOKINGS имеет неверный формат. Установлено значение по умолчанию: {MAX_PARALLEL_BOOKINGS}")

# Данные по товарам и промокодам теперь загружаются динамически из JSON-файлов
# через функции в database/db.py
