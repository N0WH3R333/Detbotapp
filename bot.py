import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler
import asyncpg

from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
import json
import aiohttp_cors
from collections import defaultdict

from config import (
    BOT_TOKEN, ADMIN_IDS, LOG_LEVEL, LOG_LEVEL_HANDLERS, LOG_LEVEL_DATABASE,
    LOG_LEVEL_AIOGRAM, LOG_DIR, LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT, SHOP_CATEGORIES,
    WEBAPP_URL, DATABASE_URL
)
from handlers import main_router
from handlers import errors # Обработчик ошибок подключаем отдельно
from database.pool import get_pool, close_pool
from database.db_setup import init_db
from database.db import (
    ensure_data_files_exist,
    get_all_products,
    get_all_promocodes
)
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
    logger.info(f"Loaded {len(all_products)} products from the database.")
    if not all_products:
        logger.warning("Products table is empty or could not be read. Returning empty catalog.")


    # Динамическое построение категорий из данных в products.json
    # Используем defaultdict для более простого и чистого кода
    categories = defaultdict(lambda: defaultdict(list))

    for product in all_products:
        category_name = (product.get("category") or "Без категории").strip() or "Без категории"
        subcategory_name = (product.get("subcategory") or "Основное").strip() or "Основное"
        categories[category_name][subcategory_name].append(product)

    # Добавляем пустые категории из конфига, если их еще нет в каталоге
    for category_name in SHOP_CATEGORIES:
        if category_name not in categories:
            categories[category_name] = defaultdict(list)
            
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
    for cat_name, subcategories in sorted(categories.items()): # Сортируем для стабильного порядка
        subcategories_list = [
            # Применяем трансформацию к каждому продукту
            {"name": sub_name, "products": [_transform_product_for_frontend(p) for p in products] if products else []}
            for sub_name, products in sorted(subcategories.items())
        ]

        response_data.append({"name": cat_name, "subcategories": subcategories_list})

    # Логируем итоговый результат перед отправкой
    num_categories = len(response_data)
    num_subcategories = sum(len(cat["subcategories"]) for cat in response_data)
    logger.info(f"Sending catalog data to frontend. "
                f"Total categories: {num_categories}, total subcategories: {num_subcategories}.")

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
    # Тестовый комментарий для проверки отображения diff
    setup_logging()

    # Проверяем наличие DATABASE_URL перед тем, как делать что-либо еще
    if not DATABASE_URL:
        logging.critical("Переменная DATABASE_URL не установлена. Бот не может запуститься без подключения к базе данных.")
        return

    # Создаем пул соединений с механизмом повторных попыток
    max_retries = 5
    retry_delay_base = 2  # seconds

    for attempt in range(1, max_retries + 1):
        try:
            await get_pool()
            logging.info("Подключение к базе данных успешно установлено.")
            break  # Выходим из цикла, если подключение успешно
        except (OSError, asyncpg.exceptions.PostgresError) as e:
            if attempt < max_retries:
                # Экспоненциальная задержка: 2, 4, 8, 16 секунд
                wait_time = retry_delay_base ** attempt
                logging.warning(
                    f"Попытка подключения к базе данных #{attempt} не удалась: {e}. "
                    f"Повторная попытка через {wait_time} секунд."
                )
                await asyncio.sleep(wait_time)
            else:
                logging.critical(f"Не удалось подключиться к БД после {max_retries} попыток: {e}")
                logging.critical("Проверьте DATABASE_URL и доступность сервера. Бот прекращает работу.")
                return  # Выход из main(), если все попытки провалились

    # Инициализируем таблицы в базе данных
    await init_db()

    # Наполняем БД начальными данными (товары) и создаем JSON-файлы.
    # Эту строку нужно выполнять только при самой первой настройке.
    # ВНИМАНИЕ: Следующая строка выполняет принудительную синхронизацию товаров из JSON-файла.
    # Это приведет к УДАЛЕНИЮ всех существующих товаров в базе данных и замене их данными из файла.
    # Раскомментируйте эту строку только для первоначального наполнения или полного обновления каталога.
    # После использования ОБЯЗАТЕЛЬНО закомментируйте ее снова, чтобы избежать случайной потери данных.
    # await force_sync_products_from_json()

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

    # Подключаем главный роутер, который содержит всю логику бота
    dp.include_router(main_router)

    # Подключаем обработчик ошибок. Он должен быть последним,
    # чтобы ловить ошибки из всех предыдущих роутеров.
    dp.include_router(errors.router)

    # Создаем веб-приложение aiohttp
    app = web.Application()

    # Добавляем API-ручки
    app.router.add_get("/api/products", products_api_handler)
    app.router.add_get("/api/validate_promocode", validate_promocode_handler)

    # Настраиваем CORS централизованно и более надежно
    if WEBAPP_URL:
        # Для отладки временно разрешаем запросы с любого источника.
        logging.info(f"CORS is configured to allow requests from: {WEBAPP_URL}")
        cors = aiohttp_cors.setup(app, defaults={
            WEBAPP_URL: aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods=["GET", "POST", "OPTIONS"],
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

        # --- Переключаемся на вебхуки для продакшена ---
        # Render предоставляет публичный URL в переменной окружения RENDER_EXTERNAL_URL
        webhook_url = os.getenv("RENDER_EXTERNAL_URL")
        if webhook_url:
            # Устанавливаем вебхук
            webhook_path = f"/webhook/{BOT_TOKEN}"
            await bot.set_webhook(f"{webhook_url}{webhook_path}")
            logging.info(f"Webhook has been set to {webhook_url}{webhook_path}")

            # Добавляем обработчик для вебхука
            from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
            handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
            handler.register(app, path=webhook_path)
            setup_application(app, dp, bot=bot)

            # Запускаем веб-сервер
            port = int(os.environ.get("PORT", 8080))
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host='0.0.0.0', port=port)
            await site.start()
            logging.info(f"Bot is running on webhook mode at http://0.0.0.0:{port}")
            await asyncio.Event().wait() # Бесконечное ожидание
        else:
            # Если запускаем локально (нет RENDER_EXTERNAL_URL), используем старый добрый поллинг
            logging.warning("RENDER_EXTERNAL_URL is not set. Running in polling mode.")
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
