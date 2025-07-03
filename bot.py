import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler

from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
import json

from config import (
    BOT_TOKEN, LOG_LEVEL, LOG_LEVEL_HANDLERS, LOG_LEVEL_DATABASE,
    LOG_LEVEL_AIOGRAM, LOG_DIR, LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT
)
from handlers import common, booking, webapp_shop, admin  # Убедитесь, что все импорты хендлеров на месте
from database.db import get_all_promocodes, get_all_products
from utils.bot_instance import bot_instance
from middlewares.block_middleware import BlockMiddleware
from utils.scheduler import scheduler, schedule_existing_reminders, schedule_reports


def setup_logging() -> None:
    """Настраивает логирование в файл и в консоль."""
    # Создаем директорию для логов, если она не существует.
    # os.makedirs с параметром exist_ok=True упрощает код.
    os.makedirs(LOG_DIR, exist_ok=True)

    log_file = os.path.join(LOG_DIR, LOG_FILE)

    # Получаем корневой логгер
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)

    # Устанавливаем уровни для конкретных модулей
    logging.getLogger("aiogram").setLevel(LOG_LEVEL_AIOGRAM)
    logging.getLogger("handlers").setLevel(LOG_LEVEL_HANDLERS)
    logging.getLogger("database").setLevel(LOG_LEVEL_DATABASE)

    # Форматтер для логов
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )

    # Обработчик для вывода в консоль
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # Обработчик для записи в файл с ротацией
    file_handler = RotatingFileHandler(
        log_file, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


async def products_api_handler(request: web.Request) -> web.Response:
    """Отдает каталог товаров в формате JSON для WebApp."""
    logger = logging.getLogger(__name__)
    logger.debug("API request for products received.")
    # Устанавливаем заголовки для CORS, на случай если фронтенд будет на другом домене
    headers = {
        "Access-Control-Allow-Origin": WEBAPP_URL or "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    products_db = await get_all_products()
    # Используем json.dumps для корректной обработки кириллицы
    return web.Response(text=json.dumps(products_db, ensure_ascii=False),
                        content_type='application/json', headers=headers)


async def validate_promocode_handler(request: web.Request) -> web.Response:
    """Проверяет валидность промокода и возвращает размер скидки."""
    logger = logging.getLogger(__name__)
    promocode = request.query.get('code', '').upper()
    logger.debug(f"API request to validate promocode: {promocode}")

    headers = {"Access-Control-Allow-Origin": WEBAPP_URL or "*"}
    promocodes_db = await get_all_promocodes()
    today = datetime.now().date()

    if promocode and promocode in promocodes_db:
        promo_data = promocodes_db[promocode]
        try:
            start_date = datetime.strptime(promo_data.get("start_date"), "%Y-%m-%d").date()
            end_date = datetime.strptime(promo_data.get("end_date"), "%Y-%m-%d").date()

            if start_date <= today <= end_date:
                # Проверка лимита использований
                usage_limit = promo_data.get("usage_limit")
                if usage_limit is not None:
                    times_used = promo_data.get("times_used", 0)
                    if times_used >= usage_limit:
                        response_data = {"valid": False, "reason": "limit_reached"}
                        logger.debug(f"Promocode {promocode} has reached its usage limit.")
                        return web.Response(text=json.dumps(response_data), content_type='application/json', headers=headers)

                discount = promo_data.get("discount")
                response_data = {"valid": True, "discount": discount}
                logger.debug(f"Promocode {promocode} is valid, discount: {discount}%")
            else:
                response_data = {"valid": False, "reason": "expired"}
                logger.debug(f"Promocode {promocode} is expired.")
        except (ValueError, KeyError, TypeError):
            response_data = {"valid": False, "reason": "invalid_format"}
            logger.warning(f"Promocode {promocode} has invalid data format: {promo_data}")
    else:
        response_data = {"valid": False}
        logger.debug(f"Promocode {promocode} is invalid.")

    return web.Response(text=json.dumps(response_data), content_type='application/json', headers=headers)

async def main() -> None:
    setup_logging()
    logging.info("Запуск бота...")

    # Инициализация бота и диспетчера
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    bot_instance.bot = bot  # Сохраняем экземпляр для доступа из других модулей
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрируем middleware для блокировки
    dp.update.outer_middleware(BlockMiddleware())

    # Подключаем роутеры
    dp.include_router(common.router)
    dp.include_router(booking.router)
    dp.include_router(webapp_shop.router)
    dp.include_router(admin.router)

    # Создаем веб-приложение aiohttp
    app = web.Application()
    # Добавляем API-ручку для получения товаров
    app.router.add_get("/api/products", products_api_handler)
    # Добавляем API-ручку для валидации промокода
    app.router.add_get("/api/validate_promocode", validate_promocode_handler)

    # Передаем экземпляр бота в диспетчер для dependency injection
    # Это позволит получать его в хэндлерах через тайп-хинтинг (bot: Bot)
    dp["bot"] = bot
    # И в веб-приложение, если понадобится
    app["bot"] = bot

    try:
        # Загружаем и планируем напоминания для существующих записей
        await schedule_existing_reminders()
        schedule_reports()
        scheduler.start()
        
        # Запускаем веб-сервер и поллинг одновременно
        runner = web.AppRunner(app)
        await runner.setup()
        # Render и другие хостинги предоставляют порт через переменную окружения PORT
        port = int(os.environ.get("PORT", 8080))
        # Укажите host и port, которые будут использоваться для WebApp
        site = web.TCPSite(runner, host='0.0.0.0', port=port)
        await site.start()
        logging.info(f"Веб-сервер для WebApp и API запущен на http://0.0.0.0:{port}")
        
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        logging.info("Остановка бота и веб-сервера...")
        scheduler.shutdown()
        await runner.cleanup()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
