import logging
from .pool import get_pool
from .schema import CREATE_TABLES_SQL

logger = logging.getLogger(__name__)

async def init_db():
    """
    Инициализирует базу данных: создает таблицы, если они не существуют.
    """
    logger.info("Инициализация схемы базы данных...")
    pool = await get_pool()
    async with pool.acquire() as connection:
        try:
            await connection.execute(CREATE_TABLES_SQL)
            logger.info("Схема базы данных успешно инициализирована.")
        except Exception as e:
            logger.critical(f"Не удалось инициализировать схему базы данных: {e}")
            raise