import json
from datetime import datetime
import logging
from aiogram import F, Router, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, User

from config import ADMIN_IDS, DELIVERY_COST
from database.db import add_order_to_db, get_all_products, get_all_promocodes, increment_promocode_usage, get_product_by_id
from keyboards.inline import get_shipping_keyboard
from keyboards.admin_inline import get_new_order_admin_keyboard

logger = logging.getLogger(__name__)
router = Router()


class OrderStates(StatesGroup):
    choosing_shipping = State()
    entering_address = State()


@router.message(F.web_app_data)
async def handle_webapp_data(message: Message, state: FSMContext):
    logger.debug(f"Received webapp data: {message.web_app_data.data}")
    try:
        data = json.loads(message.web_app_data.data)
    except json.JSONDecodeError:
        logger.error(f"Failed to decode JSON from webapp: {message.web_app_data.data}")
        await message.answer("Произошла ошибка при обработке вашего заказа. Пожалуйста, попробуйте снова.")
        return

    if data.get('action') == 'checkout':
        cart = data.get('cart', {})
        if not cart:
            await message.answer("Ваша корзина пуста.")
            return

        # Загружаем все товары и промокоды один раз
        all_products_list = await get_all_products()
        all_products_dict = {p['id']: p for p in all_products_list}
        promocodes_db = await get_all_promocodes()

        items_price = 0
        for item_id, quantity in cart.items():
            product = all_products_dict.get(item_id, {"name": "Неизвестный товар", "price": 0})
            items_price += product["price"] * quantity
        
        promocode = data.get('promocode')
        discount_percent = 0
        promo_data = promocodes_db.get(promocode) if promocode else None

        if promo_data:
            today = datetime.now().date()
            try:
                start_date = datetime.strptime(promo_data.get("start_date"), "%Y-%m-%d").date()
                end_date = datetime.strptime(promo_data.get("end_date"), "%Y-%m-%d").date()
                
                # Проверяем все условия для валидности промокода
                is_active = start_date <= today <= end_date
                usage_limit = promo_data.get("usage_limit")
                is_limit_ok = (usage_limit is None) or (promo_data.get("times_used", 0) < usage_limit)

                if is_active and is_limit_ok:
                    discount_percent = promo_data.get("discount", 0)
                else:
                    logger.warning(f"User {message.from_user.id} tried to use an invalid/expired/limit-reached promocode {promocode}.")
            except (ValueError, KeyError, TypeError):
                logger.warning(f"Promocode {promocode} has invalid data format, ignoring.")

        # Сохраняем данные заказа в FSM и запрашиваем способ доставки
        await state.update_data(
            cart=cart, 
            items_price=items_price, 
            promocode=promocode, 
            discount_percent=discount_percent
        )
        await message.answer(
            "Пожалуйста, выберите способ доставки:",
            reply_markup=get_shipping_keyboard()
        )
        await state.set_state(OrderStates.choosing_shipping)

def _build_user_confirmation_text(user_data: dict, all_products_dict: dict) -> str:
    """Формирует текст подтверждения заказа для пользователя."""
    cart = user_data.get('cart', {})
    items_price = user_data.get('items_price', 0)
    promocode = user_data.get('promocode')
    discount_amount = (items_price * user_data.get('discount_percent', 0)) / 100
    delivery_cost = user_data.get('delivery_cost', 0)
    total_price = items_price - discount_amount + delivery_cost
    shipping_method = user_data.get('shipping_method', 'Не указан')
    address = user_data.get('address')

    text = "✅ <b>Спасибо за ваш заказ!</b>\n\nВы заказали:\n"
    for item_id, quantity in cart.items():
        product = all_products_dict.get(item_id, {"name": "Неизвестный товар", "price": 0})
        text += f"• {product['name']} x {quantity} шт. = {product['price'] * quantity} руб.\n"
    
    text += f"\nСтоимость товаров: {items_price} руб.\n"
    if discount_amount > 0:
        text += f"Скидка по промокоду '{promocode}': -{discount_amount:.2f} руб.\n"
    if delivery_cost > 0:
        text += f"Стоимость доставки: {delivery_cost} руб.\n"

    text += f"\n<b>Способ получения:</b> {shipping_method}"
    if address:
        text += f"\n<b>Адрес доставки:</b> {address}"
    text += f"\n<b>Итого к оплате: {total_price:.2f} руб.</b>"
    return text

async def _notify_admins_of_new_order(bot: Bot, user: User, order: dict, all_products_dict: dict):
    """Отправляет уведомление о новом заказе администраторам."""
    if not ADMIN_IDS: return
 
    cart = order.get('cart', {})
    discount_amount = order.get('discount_amount', 0)
    delivery_cost = order.get('delivery_cost', 0)
    
    admin_text = (f"🔔 <b>Новый заказ #{order['id']}!</b>\n\n"
                  f"<b>От:</b> {user.full_name} (ID: <code>{user.id}</code>)\n"
                  f"<b>Username:</b> @{user.username or 'не указан'}\n\n<b>Состав заказа:</b>\n")
    for item_id, quantity in cart.items():
        product = all_products_dict.get(item_id, {"name": "Неизвестный товар"})
        admin_text += f"• {product['name']} x {quantity} шт.\n"
    if discount_amount > 0:
        admin_text += f"\n<b>Промокод:</b> {order.get('promocode')} (-{discount_amount:.2f} руб.)"
    if delivery_cost > 0:
        admin_text += f"\n<b>Доставка:</b> {delivery_cost} руб."
    admin_text += f"\n<b>Способ получения:</b> {order.get('shipping_method')}"
    if address := order.get('address'):
        admin_text += f"\n<b>Адрес доставки:</b> {address}"
    admin_text += f"\n<b>Итого: {order.get('total_price', 0):.2f} руб.</b>"
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text, reply_markup=get_new_order_admin_keyboard())
            logger.info(f"Admin {admin_id} has been notified about the new order from user {user.id}.")
        except Exception as e:
            logger.error(f"Failed to send notification to admin {admin_id}: {e}")

async def _finalize_order(message: Message, user: User, state: FSMContext, bot: Bot, is_callback: bool = False):
    """Внутренняя функция для завершения заказа, сохранения и отправки уведомлений."""
    # Загружаем все товары один раз, чтобы избежать многократных вызовов в цикле
    all_products_list = await get_all_products()
    all_products_dict = {p['id']: p for p in all_products_list}

    user_data = await state.get_data()
    cart = user_data.get('cart', {})
    promocode = user_data.get('promocode')
    discount_amount = (user_data.get('items_price', 0) * user_data.get('discount_percent', 0)) / 100

    # Сохраняем заказ в "базу данных"
    order_details = {
        "cart": cart, "items_price": user_data.get('items_price', 0), 
        "promocode": promocode, "discount_amount": discount_amount, 
        "delivery_cost": user_data.get('delivery_cost', 0),
        "total_price": user_data.get('items_price', 0) - discount_amount + user_data.get('delivery_cost', 0), 
        "shipping_method": user_data.get('shipping_method', 'Не указан')
    }
    if address := user_data.get('address'):
        order_details["address"] = address
    new_order = await add_order_to_db(
        user_id=user.id,
        user_full_name=user.full_name,
        user_username=user.username,
        order_details=order_details
    )

    # Инкрементируем счетчик использования промокода, если он был
    if promocode and discount_amount > 0:
        await increment_promocode_usage(promocode)

    response_text = _build_user_confirmation_text(user_data, all_products_dict)
    # Отправляем подтверждение пользователю
    if is_callback:
        await message.edit_text(response_text)
    else:
        await message.answer(response_text)

    await state.clear()

    # Уведомляем администратора
    await _notify_admins_of_new_order(bot, user, new_order, all_products_dict)


@router.callback_query(OrderStates.choosing_shipping, F.data.startswith("shipping_"))
async def shipping_chosen(callback: CallbackQuery, state: FSMContext, bot: Bot):
    shipping_method_code = callback.data.split("_")[1]

    if shipping_method_code == "delivery":
        await state.update_data(shipping_method="Доставка курьером", delivery_cost=DELIVERY_COST)
        await callback.message.edit_text(
            f"Стоимость доставки составит {DELIVERY_COST} руб.\n\n"
            "Пожалуйста, введите ваш адрес для доставки."
        )
        await state.set_state(OrderStates.entering_address)
    else:  # Самовывоз
        await state.update_data(shipping_method="Самовывоз", delivery_cost=0)
        await _finalize_order(callback.message, callback.from_user, state, bot, is_callback=True)

    await callback.answer()


@router.message(OrderStates.entering_address, F.text)
async def address_entered(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(address=message.text)
    await _finalize_order(message, message.from_user, state, bot)