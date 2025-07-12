import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Сначала загружаем основной .env файл (для совместимости)
load_dotenv()
# Затем пытаемся загрузить локальный .env.local.
# Если он существует, его переменные переопределят значения из .env
load_dotenv(dotenv_path=".env.local")

def _get_env_var(key: str, default: any, cast_to: type = str) -> any:
    """
    Безопасно получает переменную окружения, преобразует ее в нужный тип
    и возвращает значение по умолчанию в случае ошибки.
    """
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return cast_to(value)
    except (ValueError, TypeError):
        logger.warning(
            f"Переменная {key} имеет неверный формат. "
            f"Используется значение по умолчанию: {default}"
        )
        return default

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Поддержка нескольких администраторов. ID указываются в .env через запятую.
ADMIN_ID_STR = os.getenv("ADMIN_ID")
ADMIN_IDS = []
if ADMIN_ID_STR:
    ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_ID_STR.split(',') if admin_id.strip().isdigit()]

# ID главного администратора с особыми правами
SUPER_ADMIN_ID = _get_env_var("SUPER_ADMIN_ID", None, int)

LOG_LEVEL = _get_env_var("LOG_LEVEL", "INFO").upper()
LOG_LEVEL_HANDLERS = _get_env_var("LOG_LEVEL_HANDLERS", "INFO").upper()
LOG_LEVEL_AIOGRAM = _get_env_var("LOG_LEVEL_AIOGRAM", "INFO").upper()
LOG_LEVEL_DATABASE = _get_env_var("LOG_LEVEL_DATABASE", "INFO").upper()
LOG_DIR = _get_env_var("LOG_DIR", "logs")
LOG_FILE = _get_env_var("LOG_FILE", "bot.log")
WEBAPP_URL = os.getenv("WEBAPP_URL")
LOG_MAX_BYTES = _get_env_var("LOG_MAX_BYTES", 5 * 1024 * 1024, int)
LOG_BACKUP_COUNT = _get_env_var("LOG_BACKUP_COUNT", 5, int)
DELIVERY_COST = _get_env_var("DELIVERY_COST", 300, int)
REMINDER_HOURS_BEFORE = _get_env_var("REMINDER_HOURS_BEFORE", 3, int)
DAILY_REPORT_TIME = _get_env_var("DAILY_REPORT_TIME", "21:00")
WEEKLY_REPORT_DAY_OF_WEEK = _get_env_var("WEEKLY_REPORT_DAY_OF_WEEK", "sun")
WEEKLY_REPORT_TIME = _get_env_var("WEEKLY_REPORT_TIME", "22:00")
MAX_PARALLEL_BOOKINGS = _get_env_var("MAX_PARALLEL_BOOKINGS", 12, int)

# --- Database Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL")
