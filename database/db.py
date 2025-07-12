import asyncio
import json
import logging
import os
from datetime import datetime
import tempfile
from typing import Any
from .pool import get_pool

logger = logging.getLogger(__name__)

DATA_DIR = "data"
BOOKINGS_FILE = os.path.join(DATA_DIR, "bookings.json")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")
PRODUCTS_FILE = os.path.join(DATA_DIR, "products.json")
PRICES_FILE = os.path.join(DATA_DIR, "prices.json")

# Асинхронная блокировка для предотвращения гонки данных при записи в файлы
file_locks = {
    BOOKINGS_FILE: asyncio.Lock(),
    ORDERS_FILE: asyncio.Lock(),
    PRODUCTS_FILE: asyncio.Lock(),
    PRICES_FILE: asyncio.Lock(),
}

# Словарь для определения, какой пустой тип данных возвращать для каждого файла
_DEFAULT_EMPTY_VALUES = {
    BOOKINGS_FILE: [],
    ORDERS_FILE: [],
    PRODUCTS_FILE: {},
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

    if not os.path.exists(BOOKINGS_FILE):
        await _write_data(BOOKINGS_FILE, [])
    if not os.path.exists(ORDERS_FILE):
        await _write_data(ORDERS_FILE, [])
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
    if not os.path.exists(PRODUCTS_FILE):
        initial_products = {
          "autochemistry": {
            "name": "Автохимия",
            "products": [
              {
                "id": "shampoo_500",
                "name": "Супер-шампунь для авто",
                "price": 500,
                "description": "Концентрированный шампунь с воском. Придает блеск и защищает ЛКП. Объем 500 мл.",
                "imageUrl": "https://i.imgur.com/example1.png"
              },
              {
                "id": "polish_750",
                "name": "Полироль для кузова 'Антицарапин'",
                "price": 750,
                "description": "Скрывает мелкие царапины и потертости, восстанавливает глубину цвета.",
                "imageUrl": "https://i.imgur.com/example2.png"
              }
            ]
          },
          "tools": {
            "name": "Инструменты и аксессуары",
            "products": [
              {
                "id": "microfiber_250",
                "name": "Волшебная микрофибра (3 шт.)",
                "price": 250,
                "description": "Набор из трех микрофибровых полотенец разной плотности для сушки, полировки и уборки салона.",
                "imageUrl": "https://i.imgur.com/example3.png"
              }
            ]
          }
        }
        await _write_data(PRODUCTS_FILE, initial_products)



# --- Функции для работы с товарами и промокодами ---

async def get_all_products() -> dict:
    """Читает все товары из файла."""
    return await _read_data(PRODUCTS_FILE)


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
    """Ищет товар по ID во всех категориях."""
    products_db = await get_all_products()
    for category_data in products_db.values():
        for product in category_data.get('products', []):
            if product.get('id') == product_id:
                return product
    return None


# --- Функции для работы с записями (bookings) ---

async def get_all_bookings() -> list[dict]:
    """Загружает все записи на услуги из файла."""
    return await _read_data(BOOKINGS_FILE)


async def get_user_bookings(user_id: int) -> list[dict]:
    """Возвращает записи конкретного пользователя."""
    all_bookings = await get_all_bookings()
    return [b for b in all_bookings if b.get('user_id') == user_id]


async def add_booking_to_db(user_id: int, user_full_name: str, user_username: str | None, booking_data: dict) -> dict:
    """Добавляет новую запись на услугу в файл."""
    all_bookings = await get_all_bookings()
    max_id = max((b.get('id', 0) for b in all_bookings), default=0)
    new_booking = {
        'id': max_id + 1,
        'user_id': user_id,
        'user_full_name': user_full_name,
        'user_username': user_username,
        **booking_data
    }
    all_bookings.append(new_booking)
    await _write_data(BOOKINGS_FILE, all_bookings)
    logger.info(f"User {user_id} created a new booking with ID {new_booking['id']}")
    return new_booking


async def get_user_orders(user_id: int) -> list[dict]:
    """Возвращает заказы пользователя из "базы данных" (orders.json)."""
    all_orders = await _read_data(ORDERS_FILE)
    return [o for o in all_orders if o.get('user_id') == user_id]


async def get_all_orders() -> list[dict]:
    """Загружает все заказы из файла."""
    return await _read_data(ORDERS_FILE)


async def add_order_to_db(user_id: int, user_full_name: str, user_username: str | None, order_details: dict) -> dict:
    """Добавляет новый заказ в "базу данных" (orders.json) и возвращает его."""
    all_orders = await _read_data(ORDERS_FILE)
    max_id = max((order.get('id', 0) for order in all_orders), default=0)
    new_order_id = max_id + 1

    new_order = {
        "id": new_order_id,
        "user_id": user_id,
        "user_full_name": user_full_name,
        "user_username": user_username,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "В обработке",  # Добавляем статус по умолчанию
        **order_details
    }

    all_orders.append(new_order)
    await _write_data(ORDERS_FILE, all_orders)
    logger.info(f"User {user_id} placed a new order with ID {new_order_id}")
    return new_order


async def update_order_status(order_id: int, new_status: str) -> dict | None:
    """Обновляет статус заказа по его ID и возвращает обновленный заказ."""
    all_orders = await get_all_orders()
    updated_order = None
    
    for order in all_orders:
        if order.get('id') == order_id:
            order['status'] = new_status
            updated_order = order
            break
            
    if updated_order:
        await _write_data(ORDERS_FILE, all_orders)
        logger.info(f"Admin updated status for order #{order_id} to '{new_status}'")
        return updated_order
    else:
        logger.warning(f"Admin tried to update status for non-existent order #{order_id}")
        return None


async def update_order_cart_and_prices(order_id: int, new_cart: dict, new_prices: dict) -> dict | None:
    """Обновляет корзину и цены заказа по его ID."""
    all_orders = await get_all_orders()
    updated_order = None

    for order in all_orders:
        if order.get('id') == order_id:
            order['cart'] = new_cart
            order['items_price'] = new_prices.get('items_price')
            order['discount_amount'] = new_prices.get('discount_amount')
            order['total_price'] = new_prices.get('total_price')
            updated_order = order
            break

    if updated_order:
        await _write_data(ORDERS_FILE, all_orders)
        logger.info(f"Admin edited contents for order #{order_id}")
        return updated_order
    else:
        logger.warning(f"Admin tried to edit non-existent order #{order_id}")
        return None

async def cancel_booking_in_db(booking_id: int, user_id: int | None = None) -> dict | None:
    """
    Удаляет запись по ID.
    - Если user_id указан, проверяет, что запись принадлежит этому пользователю.
    - Если user_id равен None (для админа), удаляет запись по booking_id без проверки владельца.
    Возвращает удаленный объект записи в случае успеха, иначе None.
    """
    all_bookings = await get_all_bookings()
    booking_to_cancel = None

    # Находим запись для удаления
    for booking in all_bookings:
        if booking.get('id') == booking_id:
            # Если удаляет пользователь, проверяем права
            if user_id is not None and booking.get('user_id') != user_id:
                continue
            booking_to_cancel = booking
            break

    if not booking_to_cancel:
        if user_id is not None:
            logger.warning(f"Attempt to cancel non-existent or foreign booking {booking_id} by user {user_id}.")
        else:
            logger.warning(f"Admin attempt to cancel non-existent booking {booking_id}.")
        return None

    # Создаем новый список без удаленной записи
    new_bookings_list = [b for b in all_bookings if b.get('id') != booking_id]

    # Сохраняем и логируем
    await _write_data(BOOKINGS_FILE, new_bookings_list)
    log_msg_user = f"user {user_id}" if user_id is not None else "admin"
    logger.info(f"Booking {booking_id} was cancelled by {log_msg_user}.")

    return booking_to_cancel


async def cancel_order_in_db(order_id: int, user_id: int | None = None) -> dict | None:
    """
    Удаляет заказ по ID.
    - Если user_id указан, проверяет, что заказ принадлежит этому пользователю.
    - Если user_id равен None (для админа), удаляет заказ по order_id без проверки владельца.
    Возвращает удаленный объект заказа в случае успеха, иначе None.
    """
    all_orders = await get_all_orders()
    order_to_cancel = None

    # Находим заказ для удаления
    for order in all_orders:
        if order.get('id') == order_id:
            # Если удаляет пользователь, проверяем права
            if user_id is not None and order.get('user_id') != user_id:
                continue
            order_to_cancel = order
            break

    if not order_to_cancel:
        if user_id is not None:
            logger.warning(f"Attempt to cancel non-existent or foreign order {order_id} by user {user_id}.")
        else:
            logger.warning(f"Admin attempt to cancel non-existent order {order_id}.")
        return None

    # Создаем новый список без удаленного заказа
    new_orders_list = [o for o in all_orders if o.get('id') != order_id]

    # Сохраняем и логируем
    await _write_data(ORDERS_FILE, new_orders_list)
    log_msg_user = f"user {user_id}" if user_id is not None else "admin"
    logger.info(f"Order {order_id} was cancelled by {log_msg_user}.")

    return order_to_cancel


async def get_all_unique_user_ids() -> set[int]:
    """Возвращает множество всех уникальных ID пользователей из заказов и записей."""
    all_bookings = await get_all_bookings()
    all_orders = await get_all_orders()

    user_ids = set()
    for booking in all_bookings:
        if 'user_id' in booking:
            user_ids.add(booking['user_id'])
    for order in all_orders:
        if 'user_id' in order:
            user_ids.add(order['user_id'])

    return user_ids


async def get_all_unique_users() -> dict[int, dict]:
    """Возвращает словарь всех уникальных пользователей с их данными."""
    all_bookings = await get_all_bookings()
    all_orders = await get_all_orders()
    all_records = all_bookings + all_orders

    users = {}
    for record in all_records:
        user_id = record.get('user_id')
        if user_id and user_id not in users:
            users[user_id] = {
                'user_full_name': record.get('user_full_name'),
                'user_username': record.get('user_username')
            }
    return users


async def update_user_full_name(user_id: int, new_name: str) -> bool:
    """Обновляет user_full_name для пользователя во всех записях и заказах."""
    all_bookings = await get_all_bookings()
    all_orders = await get_all_orders()
    updated = False

    for booking in all_bookings:
        if booking.get('user_id') == user_id:
            booking['user_full_name'] = new_name
            updated = True

    for order in all_orders:
        if order.get('user_id') == user_id:
            order['user_full_name'] = new_name
            updated = True

    if updated:
        await _write_data(BOOKINGS_FILE, all_bookings)
        await _write_data(ORDERS_FILE, all_orders)
        logger.info(f"Updated full name for user {user_id} to '{new_name}'")

    return updated


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
        logger.warning(f"Admin attempt to delete non-existent candidate {candidate_id}.")
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