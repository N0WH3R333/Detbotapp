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

            # Дополнительная проверка и обновление ENUM типа для обратной совместимости
            # Это необходимо, если база уже была создана со старым набором статусов.
            await connection.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'pending_confirmation' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'booking_status')) THEN
                        ALTER TYPE booking_status ADD VALUE 'pending_confirmation' BEFORE 'confirmed';
                    END IF;
                END$$;
            """)
        except Exception as e:
            logger.critical(f"Не удалось инициализировать схему базы данных: {e}")
            raise