import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler

from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
import json
import aiohttp_cors

from config import (
    BOT_TOKEN, ADMIN_IDS, LOG_LEVEL, LOG_LEVEL_HANDLERS, LOG_LEVEL_DATABASE,
    LOG_LEVEL_AIOGRAM, LOG_DIR, LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT,
    WEBAPP_URL, DATABASE_URL
)
from handlers import common, booking, webapp_shop, group_management, hiring, errors
from handlers.admin import admin_router
from database.db import (
    get_all_promocodes, get_all_products, ensure_data_files_exist,
    get_all_prices, update_prices
)
from database.pool import get_pool, close_pool
from utils.bot_instance import bot_instance
from utils.constants import (CAR_SIZES, POLISHING_TYPES, CERAMICS_TYPES,
                             WRAPPING_TYPES, INTERIOR_TYPES, DIRT_LEVELS)
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

async def _ensure_price_keys_exist():
    """
    Проверяет, что для всех услуг в `prices.json` есть запись.
    Если нет, создает ее со структурой по умолчанию и нулевыми ценами.
    Это позволяет админу редактировать цены на новые услуги через существующий интерфейс.
    """
    logger = logging.getLogger(__name__)
    logger.info("Checking for missing price keys...")
    prices = await get_all_prices()

    default_structures = {
        "washing": 0,
        "glass_polishing": 0,
        "polishing": {size: {ptype: 0 for ptype in POLISHING_TYPES} for size in CAR_SIZES},
        "ceramics": {size: {ctype: 0 for ctype in CERAMICS_TYPES} for size in CAR_SIZES},
        "wrapping": {size: {wtype: 0 for wtype in WRAPPING_TYPES} for size in CAR_SIZES},
        "dry_cleaning": {size: {itype: {dlevel: 0 for dlevel in DIRT_LEVELS} for itype in INTERIOR_TYPES} for size in CAR_SIZES}
    }

    updated = False
    # Итерируемся по ключам словаря default_structures как по источнику правды
    for key in default_structures.keys():
        if key not in prices:
            logger.warning(f"Price key '{key}' is missing. Creating default structure.")
            prices[key] = default_structures.get(key, 0)
            updated = True

    if updated:
        await update_prices(prices)
        logger.info("Successfully updated prices.json with missing keys.")
    else:
        logger.info("All price keys are present.")




def _create_api_response(
    data: dict | list | None,
    status: int = 200
) -> web.Response:
    """Создает aiohttp.web.Response."""
    if status == 204: # No Content
        return web.Response(status=status)
    return web.json_response(data, status=status)

async def products_api_handler(request: web.Request) -> web.Response:
    """
    Отдает каталог товаров в формате JSON для WebApp, динамически группируя по категориям и подкатегориям
    на основе данных из products.json.
    Ожидается, что у каждого товара в `products.json` есть поле "category".
    Опционально может быть поле "subcategory".
    """
    logger = logging.getLogger(__name__)

    # Логируем origin входящего запроса для отладки CORS
    origin = request.headers.get('Origin')
    logger.info(f"API request for products from origin: {origin}, method: {request.method}")

    logger.info("Processing GET request for products.")
    all_products = await get_all_products()
    # Добавляем логирование, чтобы видеть, сколько товаров загружено
    logger.info(f"Loaded {len(all_products)} products from products.json.")
    if not all_products:
        logger.warning("products.json is empty or could not be read. Returning empty catalog.")


    # Динамическое построение категорий из данных в products.json
    # Структура: { "ИмяКатегории": { "subcategories": { "ИмяПодкатегории": { "products": [...] } } } }
    categories = {}

    for product in all_products.values():
        # Используем .strip() для удаления случайных пробелов.
        category_name = product.get("category", "Без категории").strip()
        # Если подкатегория не указана, помещаем товар в подкатегорию "Основное"
        subcategory_name = product.get("subcategory", "").strip() or "Основное"

        if not category_name:
            category_name = "Без категории"

        # Создаем категорию, если ее нет
        if category_name not in categories:
            # В категории теперь только подкатегории для единой структуры
            categories[category_name] = {"subcategories": {}}

        # Создаем подкатегорию, если ее нет
        if subcategory_name not in categories[category_name]["subcategories"]:
            categories[category_name]["subcategories"][subcategory_name] = {"products": []}
        
        # Добавляем товар в его подкатегорию
        categories[category_name]["subcategories"][subcategory_name]["products"].append(product)

    # Преобразование в формат ответа, который ожидает фронтенд
    # [ { "name": "ИмяКатегории", "subcategories": [ { "name": "ИмяПодкатегории", "products": [...] } ] } ]
    
    def _transform_product_for_frontend(product: dict) -> dict:
        """
        Преобразует ключи объекта продукта в формат,
        более удобный для JavaScript (camelCase и короткие имена),
        а также заменяет HTML-теги переноса на символы новой строки.
        """
        new_product = product.copy()
        if 'image_url' in new_product:
            new_product['imageUrl'] = new_product.pop('image_url') # Стандартный camelCase для JS
        if 'detail_images' in new_product:
            new_product['detailImages'] = new_product.pop('detail_images')
        
        if 'description' in new_product and isinstance(new_product['description'], str):
            # Заменяем HTML-сущность <br> и сам тег на символ переноса строки \n,
            # который с большей вероятностью будет правильно обработан CSS на фронтенде.
            new_product['description'] = new_product['description'].replace('&lt;br&gt;', '\n').replace('<br>', '\n')

        return new_product

    response_data = []
    for cat_name, cat_data in sorted(categories.items()): # Сортируем для стабильного порядка
        subcategories_list = [
            # Применяем трансформацию к каждому продукту
            {"name": sub_name, "products": [_transform_product_for_frontend(p) for p in sub_data["products"]]}
            for sub_name, sub_data in sorted(cat_data["subcategories"].items())
        ]

        response_data.append({"name": cat_name, "subcategories": subcategories_list})

    # Логируем итоговый результат перед отправкой
    logger.info(f"Sending catalog data to frontend. Total categories: {len(response_data)}.")

    return _create_api_response(response_data)


async def validate_promocode_handler(request: web.Request) -> web.Response:
    """Проверяет валидность промокода и возвращает размер скидки."""
    logger = logging.getLogger(__name__)
    promocode = request.query.get('code', '').upper()
    origin = request.headers.get('Origin')
    logger.debug(f"API request to validate promocode '{promocode}' from origin: {origin}, method: {request.method}")

    # Guard Clause: Промокод не предоставлен или не существует
    if not promocode or promocode not in (promocodes_db := await get_all_promocodes()):
        logger.debug(f"Promocode '{promocode}' is invalid or not found.")
        return _create_api_response({"valid": False})

    promo_data = promocodes_db[promocode]
    today = datetime.now().date()

    try:
        start_date = datetime.strptime(promo_data.get("start_date"), "%Y-%m-%d").date()
        end_date = datetime.strptime(promo_data.get("end_date"), "%Y-%m-%d").date()

        # Guard Clause: Срок действия промокода истек
        if not (start_date <= today <= end_date):
            logger.debug(f"Promocode {promocode} is expired.")
            return _create_api_response({"valid": False, "reason": "expired"})

        # Guard Clause: Проверка лимита использований
        if (usage_limit := promo_data.get("usage_limit")) is not None:
            if promo_data.get("times_used", 0) >= usage_limit:
                logger.debug(f"Promocode {promocode} has reached its usage limit.")
                return _create_api_response({"valid": False, "reason": "limit_reached"})

        # Успешный случай
        discount = promo_data.get("discount")
        logger.debug(f"Promocode {promocode} is valid, discount: {discount}%")
        return _create_api_response({"valid": True, "discount": discount})

    except (ValueError, KeyError, TypeError):
        logger.warning(f"Promocode {promocode} has invalid data format: {promo_data}")
        return _create_api_response({"valid": False, "reason": "invalid_format"})

async def main() -> None:
    setup_logging()

    # Проверяем наличие DATABASE_URL перед тем, как делать что-либо еще
    if not DATABASE_URL:
        logging.critical("Переменная DATABASE_URL не установлена. Бот не может запуститься без подключения к базе данных.")
        return

    # Создаем пул соединений при старте
    await get_pool()

    await ensure_data_files_exist()

    # Добавляем предварительную проверку синтаксиса products.json для более точной диагностики
    try:
        # Используем 'utf-8-sig', чтобы автоматически обработать BOM (частая проблема в Windows)
        with open(os.path.join('data', 'products.json'), 'r', encoding='utf-8-sig') as f:
            json.load(f)
        logging.info("Pre-check of data/products.json syntax is successful.")
    except json.JSONDecodeError as e:
        logging.critical(f"FATAL ERROR in data/products.json: Invalid syntax at line {e.lineno} column {e.colno}. Details: {e.msg}")
        logging.critical("The bot cannot start with a broken products file. Please fix the file and restart.")
        return  # Останавливаем запуск, если JSON некорректен
    except FileNotFoundError:
        logging.critical("FATAL ERROR: data/products.json not found even after check. Please check permissions or file creation logic.")
        return

    await _ensure_price_keys_exist()
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

    # Подключаем обработчик ошибок. Важно, чтобы он был в основном диспетчере.
    dp.include_router(errors.router)

    # Подключаем роутеры
    dp.include_router(common.router)
    dp.include_router(booking.router)
    dp.include_router(webapp_shop.router)
    dp.include_router(group_management.router)
    dp.include_router(hiring.router)
    
    # Подключаем единый роутер админ-панели.
    dp.include_router(admin_router)

    # Создаем веб-приложение aiohttp
    app = web.Application()

    # Добавляем API-ручки
    app.router.add_get("/api/products", products_api_handler)
    app.router.add_get("/api/validate_promocode", validate_promocode_handler)

    # Настраиваем CORS централизованно и более надежно
    if WEBAPP_URL:
        logging.info(f"CORS is configured to allow requests from: {WEBAPP_URL}")
        cors = aiohttp_cors.setup(app, defaults={
            WEBAPP_URL: aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods=["GET", "OPTIONS"],
            )
        })
        # Применяем CORS ко всем роутам в приложении
        for route in list(app.router.routes()):
            cors.add(route)
    else:
        logging.warning(
            "WEBAPP_URL is not set in environment variables. "
            "CORS is not configured, which will likely cause the web app to fail."
        )
    
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
        await close_pool() # Закрываем пул соединений
        scheduler.shutdown()
        await runner.cleanup()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
