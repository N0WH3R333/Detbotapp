import asyncpg
import logging
from config import DATABASE_URL

logger = logging.getLogger(__name__)

# Глобальная переменная для хранения пула соединений (Singleton)
_pool: asyncpg.Pool | None = None

async def get_pool() -> asyncpg.Pool:
    """
    Возвращает существующий пул соединений или создает новый, если он не существует.
    Это гарантирует, что у нас есть только один пул на все приложение.
    """
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            logger.critical("DATABASE_URL не установлена! Невозможно создать пул соединений.")
            raise ValueError("DATABASE_URL is not set")
        
        _pool = await asyncpg.create_pool(dsn=DATABASE_URL)
        logger.info("Пул соединений с базой данных успешно создан.")
    return _pool

async def close_pool():
    """Закрывает пул соединений при остановке приложения."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Пул соединений с базой данных закрыт.")