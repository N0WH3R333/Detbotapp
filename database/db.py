import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = "data"
BOOKINGS_FILE = os.path.join(DATA_DIR, "bookings.json")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")
BLOCKED_USERS_FILE = os.path.join(DATA_DIR, "blocked_users.json")
PRODUCTS_FILE = os.path.join(DATA_DIR, "products.json")
PROMOCODES_FILE = os.path.join(DATA_DIR, "promocodes.json")

# Асинхронная блокировка для предотвращения гонки данных при записи в файлы
file_locks = {
    BOOKINGS_FILE: asyncio.Lock(),
    ORDERS_FILE: asyncio.Lock(),
    BLOCKED_USERS_FILE: asyncio.Lock(),
    PRODUCTS_FILE: asyncio.Lock(),
    PROMOCODES_FILE: asyncio.Lock(),
}


async def _read_data(file_path: str) -> Any:
    """Асинхронно читает данные из JSON файла с использованием блокировки."""
    lock = file_locks.get(file_path)
    if not lock:
        raise ValueError(f"No lock found for file: {file_path}")

    async with lock:
        try:
            if not os.path.exists(file_path):
                return {} if file_path.endswith('s.json') and file_path not in [BLOCKED_USERS_FILE] else []

            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error(f"Ошибка декодирования JSON в файле: {file_path}. Возвращен пустой объект.")
            return {} if file_path.endswith('s.json') and file_path not in [BLOCKED_USERS_FILE] else []
        except FileNotFoundError:
            return {} if file_path.endswith('s.json') and file_path not in [BLOCKED_USERS_FILE] else []


async def _write_data(file_path: str, data: Any) -> None:
    """Асинхронно записывает данные в JSON файл с использованием блокировки."""
    lock = file_locks.get(file_path)
    if not lock:
        raise ValueError(f"No lock found for file: {file_path}")

    async with lock:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)


async def ensure_data_files_exist():
    """Проверяет наличие файлов данных и создает их, если они отсутствуют."""
    logger.info("Проверка и создание файлов данных...")
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(BOOKINGS_FILE):
        await _write_data(BOOKINGS_FILE, [])
    if not os.path.exists(ORDERS_FILE):
        await _write_data(ORDERS_FILE, [])
    if not os.path.exists(BLOCKED_USERS_FILE):
        await _write_data(BLOCKED_USERS_FILE, [])
    if not os.path.exists(PRODUCTS_FILE):
        initial_products = {
            "autochemistry": {
                "name": "Автохимия",
                "products": {
                    "shampoo_500": {"name": "Супер-шампунь для авто", "price": 500},
                    "polish_750": {"name": "Полироль для кузова", "price": 750},
                }
            },
            "autoaccessories": {
                "name": "Автоаксессуары",
                "products": {
                    "microfiber_250": {"name": "Волшебная микрофибра (3 шт.)", "price": 250},
                }
            }
        }
        await _write_data(PRODUCTS_FILE, initial_products)
    if not os.path.exists(PROMOCODES_FILE):
        # Добавляем поля usage_limit и times_used.
        # usage_limit: null означает "без лимита".
        initial_promocodes = {
            "SALE10": {"discount": 10, "start_date": "2024-01-01", "end_date": "2099-12-31", "usage_limit": None, "times_used": 0},
            "LIMITED25": {"discount": 25, "start_date": "2024-01-01", "end_date": "2099-12-31", "usage_limit": 100, "times_used": 10}
        }
        await _write_data(PROMOCODES_FILE, initial_promocodes)



# --- Функции для работы с товарами и промокодами ---

async def get_all_products() -> dict:
    """Читает все товары из файла."""
    return await _read_data(PRODUCTS_FILE)

async def get_all_promocodes() -> dict:
    """Читает все промокоды из файла."""
    return await _read_data(PROMOCODES_FILE)

async def add_promocode_to_db(code: str, discount: int, start_date: str, end_date: str, usage_limit: int | None) -> None:
    """Добавляет или обновляет промокод в файле."""
    promocodes = await get_all_promocodes()
    promocodes[code.upper()] = {
        "discount": discount,
        "start_date": start_date,
        "end_date": end_date,
        "usage_limit": usage_limit,
        "times_used": 0  # При создании/обновлении счетчик сбрасывается
    }
    await _write_data(PROMOCODES_FILE, promocodes)


async def increment_promocode_usage(code: str) -> None:
    """Увеличивает счетчик использования промокода на 1."""
    if not code:
        return
    promocodes = await get_all_promocodes()
    promo_data = promocodes.get(code.upper())
    if promo_data:
        promo_data['times_used'] = promo_data.get('times_used', 0) + 1
        await _write_data(PROMOCODES_FILE, promocodes)
        logger.info(f"Incremented usage count for promocode {code.upper()}.")


async def get_product_by_id(product_id: str) -> dict | None:
    """Ищет товар по ID во всех категориях."""
    products_db = await get_all_products()
    for category in products_db.values():
        # Ищем товар в словаре 'products' текущей категории
        if product_id in category.get('products', {}):
            return category['products'][product_id]
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


async def get_blocked_users() -> list[int]:
    """Возвращает список ID заблокированных пользователей."""
    return await _read_data(BLOCKED_USERS_FILE)


async def block_user(user_id: int):
    """Добавляет пользователя в черный список."""
    blocked_users = await get_blocked_users()
    if user_id not in blocked_users:
        blocked_users.append(user_id)
        await _write_data(BLOCKED_USERS_FILE, blocked_users)
        logger.info(f"User {user_id} has been blocked.")


async def unblock_user(user_id: int):
    """Удаляет пользователя из черного списка."""
    blocked_users = await get_blocked_users()
    if user_id in blocked_users:
        blocked_users.remove(user_id)
        await _write_data(BLOCKED_USERS_FILE, blocked_users)