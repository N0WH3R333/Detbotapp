import asyncio
import json
import logging
import os
from datetime import datetime
import tempfile
from typing import Any
from .pool import get_pool

class SlotAlreadyBookedError(Exception):
    """Исключение для случаев, когда временной слот уже полностью забронирован."""
    pass


logger = logging.getLogger(__name__)

DATA_DIR = "data"
PRICES_FILE = os.path.join(DATA_DIR, "prices.json")

# Асинхронная блокировка для предотвращения гонки данных при записи в файлы
file_locks = {
    PRICES_FILE: asyncio.Lock(),
}

# Словарь для определения, какой пустой тип данных возвращать для каждого файла
_DEFAULT_EMPTY_VALUES = {
    PRICES_FILE: {},
}

async def _read_data(file_path: str) -> Any:
    """Асинхронно читает данные из JSON файла с использованием блокировки."""
    lock = file_locks.get(file_path)
    if not lock:
        raise ValueError(f"No lock found for file: {file_path}")

    default_value = _DEFAULT_EMPTY_VALUES.get(file_path, [])

    async with lock:
        if not os.path.exists(file_path):
            return default_value
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Обработка случая, когда файл пуст, но существует
                return data if data else default_value
        except json.JSONDecodeError:
            logger.error(f"Ошибка декодирования JSON в файле: {file_path}. Возвращен пустой объект.")
            return default_value


async def _write_data(file_path: str, data: Any) -> None:
    """Асинхронно записывает данные в JSON файл с использованием блокировки и атомарной записи."""
    lock = file_locks.get(file_path)
    if not lock:
        raise ValueError(f"No lock found for file: {file_path}")

    async with lock:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        # Используем временный файл и атомарное переименование для безопасной записи
        temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(file_path))
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as temp_f:
                json.dump(data, temp_f, ensure_ascii=False, indent=4)
            os.replace(temp_path, file_path)
        except Exception as e:
            logger.error(f"Ошибка при записи в файл {file_path}: {e}")
            os.remove(temp_path) # Удаляем временный файл в случае ошибки
            raise


async def ensure_data_files_exist():
    """Проверяет наличие файлов данных и создает их, если они отсутствуют."""
    logger.info("Проверка и создание файлов данных...")
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(PRICES_FILE):
        initial_prices = {
            "polishing": {
                "small": {"light_polishing": 3000, "deep_polishing": 6000, "presale_polishing": 2500},
                "medium": {"light_polishing": 4000, "deep_polishing": 8000, "presale_polishing": 3500},
                "large": {"light_polishing": 5000, "deep_polishing": 10000, "presale_polishing": 4500},
            },
            "ceramics": {
                "small": {"presale_ceramics": 5000, "medium_ceramics": 10000, "long_ceramics": 15000},
                "medium": {"presale_ceramics": 6000, "medium_ceramics": 12000, "long_ceramics": 18000},
                "large": {"presale_ceramics": 7000, "medium_ceramics": 14000, "long_ceramics": 21000},
            },
            "dry_cleaning": {
                "small": {
                    "fabric": {"light": 2000, "medium": 3000, "strong": 4000},
                    "leather": {"light": 2500, "medium": 3500, "strong": 4500},
                    "alcantara": {"light": 3000, "medium": 4000, "strong": 5000},
                    "combined": {"light": 2800, "medium": 3800, "strong": 4800},
                },
                "medium": {
                    "fabric": {"light": 3000, "medium": 4000, "strong": 5000},
                    "leather": {"light": 3500, "medium": 4500, "strong": 5500},
                    "alcantara": {"light": 4000, "medium": 5000, "strong": 6000},
                    "combined": {"light": 3800, "medium": 4800, "strong": 5800},
                },
                "large": {
                    "fabric": {"light": 4000, "medium": 5000, "strong": 6000},
                    "leather": {"light": 4500, "medium": 5500, "strong": 6500},
                    "alcantara": {"light": 5000, "medium": 6000, "strong": 7000},
                    "combined": {"light": 4800, "medium": 5800, "strong": 6800},
                },
            },
            "wrapping": 50000, "washing": 1500, "glass_polishing": 4000,
        }
        await _write_data(PRICES_FILE, initial_prices)
    await _seed_initial_products()


async def _seed_initial_products():
    """Наполняет таблицы товаров и категорий начальными данными, если они пусты."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        count = await connection.fetchval("SELECT COUNT(*) FROM products")
        if count > 0:
            return

        logger.info("Таблицы товаров пусты. Наполняем начальными данными...")
        initial_products_data = {
            "autochemistry": {
                "name": "Автохимия",
                "products": [
                    {
                        "id": "shampoo_500", "name": "Супер-шампунь для авто", "price": 500,
                        "description": "Концентрированный шампунь с воском. Придает блеск и защищает ЛКП. Объем 500 мл.",
                        "image_url": "https://i.imgur.com/example1.png"
                    },
                    {
                        "id": "polish_750", "name": "Полироль для кузова 'Антицарапин'", "price": 750,
                        "description": "Скрывает мелкие царапины и потертости, восстанавливает глубину цвета.",
                        "image_url": "https://i.imgur.com/example2.png"
                    }
                ]
            },
            "tools": {
                "name": "Инструменты и аксессуары",
                "products": [
                    {
                        "id": "microfiber_250", "name": "Волшебная микрофибра (3 шт.)", "price": 250,
                        "description": "Набор из трех микрофибровых полотенец разной плотности для сушки, полировки и уборки салона.",
                        "image_url": "https://i.imgur.com/example3.png"
                    }
                ]
            }
        }

        async with connection.transaction():
            for category_id, category_data in initial_products_data.items():
                await connection.execute(
                    "INSERT INTO product_categories (id, name) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING",
                    category_id, category_data['name']
                )
                for product in category_data['products']:
                    await connection.execute(
                        """
                        INSERT INTO products (id, name, price, description, image_url, category_id, subcategory, detail_images)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        """,
                        product['id'],
                        product['name'],
                        product['price'],
                        product.get('description'),
                        product.get('image_url'),
                        category_id,
                        product.get('subcategory'),
                        json.dumps(product.get('detail_images')) if product.get('detail_images') else None
                    )
        logger.info("Начальные данные для товаров успешно загружены в базу данных.")

async def add_admin(user_id: int) -> bool:
    """Делает пользователя администратором."""
    pool = await get_pool()
    # Сначала убедимся, что пользователь существует в таблице users.
    # Если нет, мы не можем сделать его админом.
    async with pool.acquire() as connection:
        user_exists = await connection.fetchval("SELECT 1 FROM users WHERE user_id = $1", user_id)
        if not user_exists:
            logger.warning(f"Попытка добавить в админы несуществующего пользователя с ID {user_id}")
            return False

        await connection.execute("UPDATE users SET is_admin = TRUE WHERE user_id = $1", user_id)
        logger.info(f"Пользователь {user_id} назначен администратором.")
        return True


async def remove_admin(user_id: int) -> bool:
    """Убирает права администратора у пользователя."""
    pool = await get_pool()
    result = await pool.execute("UPDATE users SET is_admin = FALSE WHERE user_id = $1", user_id)
    if result == "UPDATE 1":
        logger.info(f"Пользователь {user_id} лишен прав администратора.")
        return True
    return False


async def get_admin_list() -> list[dict]:
    """Возвращает список всех администраторов из БД."""
    pool = await get_pool()
    records = await pool.fetch("SELECT user_id, full_name, username FROM users WHERE is_admin = TRUE")
    return [dict(rec) for rec in records]

# --- Функции для работы с товарами и промокодами ---

async def get_all_products() -> list[dict]:
    """Читает все товары из базы данных, объединяя с категориями."""
    pool = await get_pool()
    sql = """
        SELECT
            p.id, p.name, p.price, p.description, p.image_url, p.detail_images, p.subcategory,
            pc.name as category
        FROM products p
        JOIN product_categories pc ON p.category_id = pc.id
        ORDER BY pc.name, p.subcategory, p.name;
    """
    async with pool.acquire() as connection:
        records = await connection.fetch(sql)
        # Преобразуем asyncpg.Record в словари и парсим JSONB поля
        products = []
        for rec in records:
            product_dict = dict(rec)
            if product_dict.get('detail_images') and isinstance(product_dict['detail_images'], str):
                product_dict['detail_images'] = json.loads(product_dict['detail_images'])
            products.append(product_dict)
        return products


async def get_all_prices() -> dict:
    """Читает все цены из файла."""
    return await _read_data(PRICES_FILE)

async def update_prices(new_prices_data: dict) -> None:
    """Полностью перезаписывает файл с ценами."""
    await _write_data(PRICES_FILE, new_prices_data)


async def add_blocked_date(date_str: str) -> None:
    """Добавляет дату в список заблокированных в БД."""
    pool = await get_pool()
    # TO_DATE преобразует строку в тип DATE, который хранится в БД
    sql = "INSERT INTO blocked_dates (blocked_date) VALUES (TO_DATE($1, 'DD.MM.YYYY')) ON CONFLICT DO NOTHING;"
    async with pool.acquire() as connection:
        await connection.execute(sql, date_str)
    logger.info(f"Date {date_str} has been blocked by admin.")

async def remove_blocked_date(date_str: str) -> None:
    """Удаляет дату из списка заблокированных в БД."""
    pool = await get_pool()
    sql = "DELETE FROM blocked_dates WHERE blocked_date = TO_DATE($1, 'DD.MM.YYYY');"
    async with pool.acquire() as connection:
        await connection.execute(sql, date_str)
    logger.info(f"Date {date_str} has been unblocked by admin.")

async def get_blocked_dates() -> list[str]:
    """Возвращает список заблокированных дат из БД в формате 'dd.mm.yyyy'."""
    pool = await get_pool()
    sql = "SELECT TO_CHAR(blocked_date, 'DD.MM.YYYY') as blocked_date FROM blocked_dates;"
    async with pool.acquire() as connection:
        records = await connection.fetch(sql)
        return [rec['blocked_date'] for rec in records]

# --- Новые функции для работы с промокодами через PostgreSQL ---

async def get_all_promocodes() -> dict:
    """Читает все промокоды из базы данных и возвращает их в виде словаря."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        records = await connection.fetch("SELECT * FROM promocodes ORDER BY created_at DESC")
        # Преобразуем список записей в словарь, как было раньше, для совместимости
        promocodes_dict = {
            rec['code']: {
                "type": rec['promo_type'],
                "discount": rec['discount_percent'],
                "start_date": rec['start_date'].strftime("%Y-%m-%d"),
                "end_date": rec['end_date'].strftime("%Y-%m-%d"),
                "usage_limit": rec['usage_limit'],
                "times_used": rec['times_used']
            } for rec in records
        }
        return promocodes_dict

async def add_promocode_to_db(code: str, discount: int, start_date: str, end_date: str, usage_limit: int | None, promo_type: str) -> None:
    """Добавляет или обновляет промокод в базе данных."""
    pool = await get_pool()
    sql = """
        INSERT INTO promocodes (code, promo_type, discount_percent, start_date, end_date, usage_limit, times_used)
        VALUES ($1, $2, $3, $4, $5, $6, 0)
        ON CONFLICT (code) DO UPDATE SET
            promo_type = EXCLUDED.promo_type,
            discount_percent = EXCLUDED.discount_percent,
            start_date = EXCLUDED.start_date,
            end_date = EXCLUDED.end_date,
            usage_limit = EXCLUDED.usage_limit,
            times_used = 0; -- Сбрасываем счетчик при обновлении
    """
    async with pool.acquire() as connection:
        await connection.execute(sql, code.upper(), promo_type, discount, start_date, end_date, usage_limit)
    logger.info(f"Promocode {code.upper()} was added or updated in the database.")

async def increment_promocode_usage(code: str) -> None:
    """Увеличивает счетчик использования промокода на 1 в базе данных."""
    if not code:
        return
    pool = await get_pool()
    sql = "UPDATE promocodes SET times_used = times_used + 1 WHERE code = $1;"
    async with pool.acquire() as connection:
        result = await connection.execute(sql, code.upper())
        if result == "UPDATE 1":
             logger.info(f"Incremented usage count for promocode {code.upper()}.")
        else:
             logger.warning(f"Attempted to increment usage for non-existent promocode {code.upper()}.")


async def get_product_by_id(product_id: str) -> dict | None:
    """Ищет товар по ID в базе данных."""
    pool = await get_pool()
    sql = "SELECT * FROM products WHERE id = $1;"
    async with pool.acquire() as connection:
        record = await connection.fetchrow(sql, product_id)
        if record:
            return dict(record)
        return None

# --- Функции для работы с записями (bookings) ---

async def _format_booking_record(record: dict) -> dict:
    """Вспомогательная функция для форматирования записи из БД в привычный dict."""
    # Преобразуем asyncpg.Record в обычный словарь
    booking = dict(record)
    # Для совместимости с остальным кодом, который ожидает 'id', а не 'booking_id'
    booking['id'] = booking['booking_id']
    # Форматируем дату и время в строки, как было в JSON
    if 'booking_date' in booking and booking['booking_date']:
        booking['date'] = booking['booking_date'].strftime('%d.%m.%Y')
    if 'booking_time' in booking and booking['booking_time']:
        booking['time'] = booking['booking_time'].strftime('%H:%M')
    # Распаковываем JSONB с деталями в основной словарь
    if 'details_json' in booking and booking['details_json']:
        # booking['details_json'] может быть строкой или уже dict
        details = json.loads(booking['details_json']) if isinstance(booking['details_json'], str) else booking['details_json']
        booking.update(details)
    # Добавляем медиафайлы
    if 'media_files' in booking and isinstance(booking['media_files'], str):
        booking['media_files'] = json.loads(booking['media_files'])
    elif 'media_files' not in booking:
        booking['media_files'] = []

    return booking

async def get_all_bookings() -> list[dict]:
    """Загружает все активные записи на услуги из базы данных."""
    pool = await get_pool()
    # Используем LEFT JOIN и агрегацию JSON, чтобы получить все медиафайлы одним запросом
    sql = """
        SELECT b.*, u.full_name as user_full_name, u.username as user_username,
               COALESCE(
                   (SELECT json_agg(json_build_object('type', bm.file_type, 'file_id', bm.file_id))
                    FROM booking_media bm WHERE bm.booking_id = b.booking_id),
                   '[]'::json
               ) as media_files
        FROM bookings b
        JOIN users u ON b.user_id = u.user_id
        WHERE b.status NOT IN ('cancelled_by_user', 'cancelled_by_admin', 'completed')
        ORDER BY b.booking_date, b.booking_time;
    """
    async with pool.acquire() as connection:
        records = await connection.fetch(sql)
        return [await _format_booking_record(rec) for rec in records]

async def get_bookings_for_occupancy() -> list[dict]:
    """
    Загружает все записи, которые влияют на занятость слотов ('pending_confirmation', 'confirmed').
    Возвращает только необходимые для подсчета поля для эффективности.
    """
    pool = await get_pool()
    sql = """
        SELECT booking_date, booking_time
        FROM bookings
        WHERE status IN ('pending_confirmation', 'confirmed');
    """
    async with pool.acquire() as connection:
        records = await connection.fetch(sql)
        return [
            {'date': rec['booking_date'].strftime('%d.%m.%Y'), 'time': rec['booking_time'].strftime('%H:%M')}
            for rec in records
        ]

async def get_user_bookings(user_id: int) -> list[dict]:
    """Возвращает все активные и ожидающие подтверждения записи пользователя из БД."""
    pool = await get_pool()
    sql = """
        SELECT b.*,
               COALESCE(
                   (SELECT json_agg(json_build_object('type', bm.file_type, 'file_id', bm.file_id))
                    FROM booking_media bm WHERE bm.booking_id = b.booking_id),
                   '[]'::json
               ) as media_files
        FROM bookings b
        WHERE b.user_id = $1 AND b.status IN ('pending_confirmation', 'confirmed')
        ORDER BY b.created_at DESC;
    """
    async with pool.acquire() as connection:
        records = await connection.fetch(sql, user_id)
        return [await _format_booking_record(rec) for rec in records]

async def add_booking_to_db(user_id: int, user_full_name: str, user_username: str | None, booking_data: dict) -> dict:
    """
    Добавляет новую запись на услугу в базу данных.
    Проверяет, что на указанное время есть свободные слоты (максимум 2 записи).
    """
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            # 1. Проверяем количество существующих записей на это же время
            time_obj = datetime.strptime(booking_data['time'], '%H:%M').time()
            date_str = booking_data['date']

            count_sql = """
                SELECT COUNT(*) FROM bookings
                WHERE booking_date = TO_DATE($1, 'DD.MM.YYYY')
                  AND booking_time = $2
                  AND status IN ('pending_confirmation', 'confirmed');
            """
            count = await connection.fetchval(count_sql, date_str, time_obj)

            if count >= 2:
                logger.warning(f"Попытка записи на уже занятый слот: {date_str} {booking_data['time']} пользователем {user_id}")
                raise SlotAlreadyBookedError(f"Слот на {date_str} {booking_data['time']} уже полностью занят.")

            # 2. Убедимся, что пользователь существует и обновим его данные, включая номер телефона
            phone_number = booking_data.get("phone_number")
            await connection.execute(
                """
                INSERT INTO users (user_id, full_name, username, phone_number) 
                VALUES ($1, $2, $3, $4) 
                ON CONFLICT (user_id) DO UPDATE SET 
                    full_name = EXCLUDED.full_name, 
                    username = EXCLUDED.username,
                    phone_number = COALESCE(EXCLUDED.phone_number, users.phone_number);
                """,
                user_id, user_full_name, user_username, phone_number
            )

            # 3. Добавляем основную запись
            booking_sql = """
                INSERT INTO bookings (user_id, service_name, booking_date, booking_time, price_rub, discount_rub, promocode, details_json)
                VALUES ($1, $2, TO_DATE($3, 'DD.MM.YYYY'), $4, $5, $6, $7, $8)
                RETURNING booking_id;
            """

            booking_id = await connection.fetchval(
                booking_sql, user_id, booking_data['service'], booking_data['date'], time_obj,
                int(booking_data['price']), int(booking_data.get('discount_amount', 0)),
                booking_data.get('promocode'), json.dumps(booking_data.get('details', {}))
            )

            # 4. Добавляем медиафайлы, если они есть
            media_files = booking_data.get('media_files', [])
            if media_files:
                media_sql = "INSERT INTO booking_media (booking_id, file_id, file_type) VALUES ($1, $2, $3);"
                media_data = [(booking_id, media['file_id'], media['type']) for media in media_files]
                await connection.executemany(media_sql, media_data)

    # Возвращаем созданную запись для дальнейшего использования (например, для уведомлений)
    new_booking = {**booking_data, 'id': booking_id, 'user_id': user_id, 'user_full_name': user_full_name, 'user_username': user_username}
    logger.info(f"User {user_id} created a new booking with ID {booking_id}")
    return new_booking

async def get_booking_by_id(booking_id: int) -> dict | None:
    """Загружает одну запись по её ID со всей связанной информацией."""
    pool = await get_pool()
    sql = """
        SELECT b.*, 
               u.full_name as user_full_name, 
               u.phone_number as user_phone_number,
               u.username as user_username,
               u.is_blocked as user_is_blocked,
               u.internal_note as user_internal_note,
               COALESCE(
                   (SELECT json_agg(json_build_object('type', bm.file_type, 'file_id', bm.file_id))
                    FROM booking_media bm WHERE bm.booking_id = b.booking_id),
                   '[]'::json
               ) as media_files
        FROM bookings b
        JOIN users u ON b.user_id = u.user_id
        WHERE b.booking_id = $1;
    """
    async with pool.acquire() as connection:
        record = await connection.fetchrow(sql, booking_id)
        if record:
            return await _format_booking_record(record)
        return None

async def update_booking_status(booking_id: int, new_status: str) -> dict | None:
    """Обновляет статус записи по её ID в БД и возвращает обновленную запись."""
    pool = await get_pool()
    # Проверяем, что новый статус валиден для ENUM типа
    valid_statuses = ('pending_confirmation', 'confirmed', 'completed', 'cancelled_by_user', 'cancelled_by_admin')
    if new_status not in valid_statuses:
        logger.error(f"Attempted to set invalid booking status '{new_status}' for booking #{booking_id}")
        return None

    sql = "UPDATE bookings SET status = $1 WHERE booking_id = $2 RETURNING *;"
    async with pool.acquire() as connection:
        updated_record = await connection.fetchrow(sql, new_status, booking_id)

    if updated_record:
        logger.info(f"Updated status for booking #{booking_id} to '{new_status}'")
        # Используем существующую функцию для форматирования, чтобы вернуть консистентные данные
        return await _format_booking_record(updated_record)
    return None


async def update_user_note(user_id: int, note: str) -> bool:
    """Обновляет или добавляет внутреннюю заметку для пользователя."""
    pool = await get_pool()
    sql = "UPDATE users SET internal_note = $1 WHERE user_id = $2;"
    async with pool.acquire() as connection:
        result = await connection.execute(sql, note, user_id)
    
    if result == "UPDATE 1":
        logger.info(f"Updated internal note for user {user_id}.")
        return True
    else:
        # Если пользователь не найден, ничего страшного, просто логируем
        logger.warning(f"Failed to update internal note for user {user_id} (user may not exist).")
        return False

def _format_order_record(record: dict) -> dict:
    """Вспомогательная функция для форматирования записи заказа из БД в привычный dict."""
    order = dict(record)
    order['id'] = order['order_id']  # для совместимости

    # Восстанавливаем корзину из агрегированного JSON
    items_list = json.loads(order['items']) if isinstance(order['items'], str) else order['items']
    order['cart'] = {item['product_id']: item['quantity'] for item in items_list}

    # Для совместимости со старым кодом, который ожидает эти ключи
    order['date'] = order['created_at'].strftime("%Y-%m-%d %H:%M:%S")
    order['items_price'] = order.get('items_price_rub', 0)
    order['delivery_cost'] = order.get('delivery_cost_rub', 0)
    order['discount_amount'] = order.get('discount_rub', 0)
    order['total_price'] = order.get('total_price_rub', 0)
    order['address'] = order.get('shipping_address')

    # Удаляем вспомогательные/дублирующиеся поля
    del order['items']
    del order['order_id']
    del order['items_price_rub']
    del order['delivery_cost_rub']
    del order['discount_rub']
    del order['total_price_rub']
    del order['shipping_address']

    return order

async def get_user_orders(user_id: int) -> list[dict]:
    """Возвращает все заказы конкретного пользователя из БД."""
    pool = await get_pool()
    sql = """
        SELECT o.*,
               COALESCE(
                   (SELECT json_agg(json_build_object('product_id', oi.product_id, 'quantity', oi.quantity))
                    FROM order_items oi WHERE oi.order_id = o.order_id),
                   '[]'::json
               ) as items
        FROM orders o
        WHERE o.user_id = $1
        ORDER BY o.created_at DESC;
    """
    async with pool.acquire() as connection:
        records = await connection.fetch(sql, user_id)
        return [_format_order_record(rec) for rec in records]

async def get_all_orders() -> list[dict]:
    """Загружает все заказы из базы данных."""
    pool = await get_pool()
    sql = """
        SELECT o.*, u.full_name as user_full_name, u.username as user_username,
               COALESCE(
                   (SELECT json_agg(json_build_object('product_id', oi.product_id, 'quantity', oi.quantity, 'price_per_item', oi.price_per_item_rub))
                    FROM order_items oi WHERE oi.order_id = o.order_id),
                   '[]'::json
               ) as items
        FROM orders o
        JOIN users u ON o.user_id = u.user_id
        ORDER BY o.created_at DESC;
    """
    async with pool.acquire() as connection:
        records = await connection.fetch(sql)
        return [_format_order_record(rec) for rec in records]

async def add_order_to_db(user_id: int, user_full_name: str, user_username: str | None, order_details: dict) -> dict:
    """Добавляет новый заказ и его состав в базу данных в рамках одной транзакции."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            # 1. Убедимся, что пользователь существует
            await connection.execute(
                "INSERT INTO users (user_id, full_name, username) VALUES ($1, $2, $3) ON CONFLICT (user_id) DO UPDATE SET full_name = EXCLUDED.full_name, username = EXCLUDED.username;",
                user_id, user_full_name, user_username
            )

            # 2. Добавляем основную информацию о заказе
            order_sql = """
                INSERT INTO orders (user_id, items_price_rub, delivery_cost_rub, discount_rub, total_price_rub, promocode, shipping_method, shipping_address)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING order_id, created_at;
            """
            order_record = await connection.fetchrow(
                order_sql, user_id, int(order_details['items_price']), int(order_details['delivery_cost']),
                int(order_details['discount_amount']), int(order_details['total_price']),
                order_details.get('promocode'), order_details.get('shipping_method'), order_details.get('address')
            )
            order_id = order_record['order_id']

            # 3. Добавляем товары из корзины
            cart = order_details.get('cart', {})
            if cart:
                # Получаем цены всех товаров в корзине одним запросом
                product_ids = list(cart.keys())
                products_in_cart = await connection.fetch("SELECT id, price FROM products WHERE id = ANY($1::text[])", product_ids)
                prices_map = {p['id']: p['price'] for p in products_in_cart}

                items_to_insert = []
                for product_id, quantity in cart.items():
                    price_per_item = prices_map.get(product_id, 0) # Цена на момент покупки
                    items_to_insert.append((order_id, product_id, quantity, price_per_item))

                items_sql = "INSERT INTO order_items (order_id, product_id, quantity, price_per_item_rub) VALUES ($1, $2, $3, $4);"
                await connection.executemany(items_sql, items_to_insert)

    # Формируем и возвращаем объект, совместимый со старым кодом
    new_order = {
        "id": order_id, "user_id": user_id, "user_full_name": user_full_name,
        "user_username": user_username, "date": order_record['created_at'].strftime("%Y-%m-%d %H:%M:%S"),
        "status": "processing", **order_details
    }
    logger.info(f"User {user_id} placed a new order with ID {order_id}")
    return new_order

async def update_order_status(order_id: int, new_status: str) -> dict | None:
    """Обновляет статус заказа по его ID в БД и возвращает обновленный заказ."""
    pool = await get_pool()
    sql = "UPDATE orders SET status = $1 WHERE order_id = $2 RETURNING *;"
    async with pool.acquire() as connection:
        # Мы не можем использовать _format_order_record, т.к. он требует JOIN,
        # а здесь простой UPDATE. Мы вернем базовые данные, админ-панель их обработает.
        updated_record = await connection.fetchrow(sql, new_status, order_id)

    if updated_record:
        logger.info(f"Admin updated status for order #{order_id} to '{new_status}'")
        return dict(updated_record)
    else:
        logger.warning(f"Admin tried to update status for non-existent order #{order_id}")
        return None

async def update_order_cart_and_prices(order_id: int, new_cart: dict, new_prices: dict) -> dict | None:
    """Обновляет корзину и цены заказа по его ID в БД в рамках транзакции."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            # 1. Обновляем цены в основной таблице
            update_sql = """
                UPDATE orders SET
                    items_price_rub = $1,
                    discount_rub = $2,
                    total_price_rub = $3
                WHERE order_id = $4
                RETURNING *;
            """
            updated_record = await connection.fetchrow(
                update_sql, int(new_prices['items_price']), int(new_prices['discount_amount']),
                int(new_prices['total_price']), order_id
            )
            if not updated_record:
                logger.warning(f"Admin tried to edit non-existent order #{order_id}")
                return None

            # 2. Удаляем старые товары
            await connection.execute("DELETE FROM order_items WHERE order_id = $1;", order_id)

            # 3. Добавляем новые товары
            if new_cart:
                product_ids = list(new_cart.keys())
                products_in_cart = await connection.fetch("SELECT id, price FROM products WHERE id = ANY($1::text[])", product_ids)
                prices_map = {p['id']: p['price'] for p in products_in_cart}

                items_to_insert = [
                    (order_id, pid, qty, prices_map.get(pid, 0)) for pid, qty in new_cart.items()
                ]
                items_sql = "INSERT INTO order_items (order_id, product_id, quantity, price_per_item_rub) VALUES ($1, $2, $3, $4);"
                await connection.executemany(items_sql, items_to_insert)

    logger.info(f"Admin edited contents for order #{order_id}")
    return dict(updated_record)

async def cancel_booking_in_db(booking_id: int, user_id: int | None = None) -> dict | None:
    """
    Отменяет запись, обновляя ее статус в БД.
    - Если user_id указан, статус меняется на 'cancelled_by_user' и проверяется владелец.
    - Если user_id равен None (для админа), статус меняется на 'cancelled_by_admin'.
    Возвращает отмененный объект записи в случае успеха, иначе None.
    """
    pool = await get_pool()
    new_status = 'cancelled_by_user' if user_id is not None else 'cancelled_by_admin'
    
    sql = "UPDATE bookings SET status = $1 WHERE booking_id = $2"
    # Если отменяет пользователь, добавляем проверку, что он владелец записи
    if user_id:
        sql += " AND user_id = $3"
    sql += " RETURNING *;"

    async with pool.acquire() as connection:
        params = [new_status, booking_id]
        if user_id:
            params.append(user_id)
        
        cancelled_record = await connection.fetchrow(sql, *params)

    if cancelled_record:
        log_msg_user = f"user {user_id}" if user_id is not None else "admin"
        logger.info(f"Booking {booking_id} was cancelled by {log_msg_user}. Status set to '{new_status}'.")
        return await _format_booking_record(cancelled_record)
    else:
        if user_id is not None:
            logger.warning(f"Attempt to cancel non-existent or foreign booking {booking_id} by user {user_id}.")
        else:
            logger.warning(f"Admin attempt to cancel non-existent booking {booking_id}.")
        return None


async def cancel_order_in_db(order_id: int, user_id: int | None = None) -> dict | None:
    """
    Отменяет заказ, обновляя его статус на 'cancelled'.
    - Если user_id указан, проверяет, что заказ принадлежит этому пользователю.
    Возвращает отмененный объект заказа в случае успеха, иначе None.
    """
    pool = await get_pool()
    sql = "UPDATE orders SET status = 'cancelled' WHERE order_id = $1"
    if user_id:
        sql += " AND user_id = $2"
    sql += " RETURNING *;"

    async with pool.acquire() as connection:
        params = [order_id]
        if user_id:
            params.append(user_id)
        
        cancelled_record = await connection.fetchrow(sql, *params)

    if cancelled_record:
        log_msg_user = f"user {user_id}" if user_id is not None else "admin"
        logger.info(f"Order {order_id} was cancelled by {log_msg_user}. Status set to 'cancelled'.")
        # Мы не можем здесь вызвать _format_order_record, т.к. нет JOIN'а.
        # Возвращаем базовые данные, хендлеру этого достаточно для уведомления.
        return dict(cancelled_record)
    else:
        if user_id is not None:
            logger.warning(f"Attempt to cancel non-existent or foreign order {order_id} by user {user_id}.")
        else:
            logger.warning(f"Admin attempt to cancel non-existent order {order_id}.")
        return None


async def get_all_unique_user_ids() -> set[int]:
    """Возвращает множество всех уникальных ID пользователей из заказов и записей."""
    pool = await get_pool()
    # Запрос к БД гораздо эффективнее, чем загрузка всех данных в память
    sql = """
        SELECT user_id FROM bookings
        UNION
        SELECT user_id FROM orders;
    """
    async with pool.acquire() as connection:
        records = await connection.fetch(sql)
        return {rec['user_id'] for rec in records}


async def get_all_unique_users() -> dict[int, dict]:
    """Возвращает словарь всех уникальных пользователей с их данными из таблицы users."""
    pool = await get_pool()
    sql = "SELECT user_id, full_name as user_full_name, username as user_username FROM users;"
    async with pool.acquire() as connection:
        records = await connection.fetch(sql)
        return {rec['user_id']: dict(rec) for rec in records}


async def update_user_full_name(user_id: int, new_name: str) -> bool:
    """Обновляет full_name для пользователя в таблице users."""
    pool = await get_pool()
    sql = "UPDATE users SET full_name = $1 WHERE user_id = $2;"
    async with pool.acquire() as connection:
        result = await connection.execute(sql, new_name, user_id)

    if result == "UPDATE 1":
        logger.info(f"Updated full name for user {user_id} to '{new_name}'")
        return True
    return False


# --- Новые функции для работы с кандидатами через PostgreSQL ---

async def get_all_candidates() -> list[dict]:
    """Загружает всех кандидатов из базы данных."""
    pool = await get_pool()
    sql = "SELECT * FROM candidates ORDER BY received_at DESC;"
    async with pool.acquire() as connection:
        records = await connection.fetch(sql)
        # Преобразуем для совместимости, т.к. в старом коде id - это 'id', а не 'candidate_id'
        return [{**rec, 'id': rec['candidate_id']} for rec in records]

async def add_candidate_to_db(user_id: int, user_full_name: str, user_username: str | None, message_text: str, file_id: str | None, file_name: str | None) -> dict:
    """Добавляет нового кандидата в базу данных."""
    pool = await get_pool()
    sql = """
        INSERT INTO candidates (user_id, full_name, username, message_text, file_id, file_name)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING candidate_id, received_at;
    """
    async with pool.acquire() as connection:
        # Убедимся, что пользователь существует
        await connection.execute(
            "INSERT INTO users (user_id, full_name, username) VALUES ($1, $2, $3) ON CONFLICT (user_id) DO NOTHING;",
            user_id, user_full_name, user_username
        )
        record = await connection.fetchrow(sql, user_id, user_full_name, user_username, message_text, file_id, file_name)

    new_candidate = {
        'id': record['candidate_id'], 'user_id': user_id, 'user_full_name': user_full_name,
        'user_username': user_username, 'message_text': message_text, 'file_id': file_id,
        'file_name': file_name, 'received_at': record['received_at'].strftime("%Y-%m-%d %H:%M:%S")
    }
    logger.info(f"User {user_id} submitted a new job application with ID {new_candidate['id']}")
    return new_candidate

async def delete_candidate_in_db(candidate_id: int) -> dict | None:
    """Удаляет кандидата по ID из базы данных."""
    pool = await get_pool()
    sql = "DELETE FROM candidates WHERE candidate_id = $1 RETURNING *;"
    async with pool.acquire() as connection:
        deleted_record = await connection.fetchrow(sql, candidate_id)

    if deleted_record:
        logger.info(f"Candidate {candidate_id} was deleted by admin.")
        return {**deleted_record, 'id': deleted_record['candidate_id']}
    else:
        logger.warning(f"Admin tried to delete non-existent candidate #{candidate_id}.")
        return None

async def get_blocked_users() -> list[int]:
    """Возвращает список ID заблокированных пользователей из базы данных."""
    pool = await get_pool()
    sql = "SELECT user_id FROM users WHERE is_blocked = TRUE;"
    async with pool.acquire() as connection:
        records = await connection.fetch(sql)
        return [rec['user_id'] for rec in records]


async def block_user(user_id: int, user_full_name: str = "N/A"):
    """Блокирует пользователя, устанавливая флаг is_blocked в TRUE."""
    pool = await get_pool()
    # Мы используем ON CONFLICT, чтобы команда не падала, если пользователя еще нет в таблице.
    # В реальном приложении пользователь, скорее всего, уже будет в базе.
    sql = """
        INSERT INTO users (user_id, full_name, is_blocked)
        VALUES ($1, $2, TRUE)
        ON CONFLICT (user_id) DO UPDATE SET
            is_blocked = TRUE;
    """
    async with pool.acquire() as connection:
        await connection.execute(sql, user_id, user_full_name)
    logger.info(f"User {user_id} has been blocked.")


async def unblock_user(user_id: int):
    """Разблокирует пользователя, устанавливая флаг is_blocked в FALSE."""
    pool = await get_pool()
    sql = "UPDATE users SET is_blocked = FALSE WHERE user_id = $1;"
    async with pool.acquire() as connection:
        await connection.execute(sql, user_id)
    logger.info(f"User {user_id} has been unblocked.")