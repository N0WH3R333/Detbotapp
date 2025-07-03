import json
from datetime import datetime
import logging
from aiogram import F, Router, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, User

from config import ADMIN_ID, DELIVERY_COST
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

        items_price = 0
        for item_id, quantity in cart.items():
            # Используем новую функцию для поиска товара
            product = await get_product_by_id(item_id) or {"name": "Неизвестный товар", "price": 0}
            items_price += product["price"] * quantity
        
        promocode = data.get('promocode')
        discount_percent = 0
        if promocode:
            promocodes_db = await get_all_promocodes()
            promo_data = promocodes_db.get(promocode)
            if promo_data:
                today = datetime.now().date()
                try:
                    start_date = datetime.strptime(promo_data.get("start_date"), "%Y-%m-%d").date()
                    end_date = datetime.strptime(promo_data.get("end_date"), "%Y-%m-%d").date()
                    if start_date <= today <= end_date:
                        # Проверка лимита
                        usage_limit = promo_data.get("usage_limit")
                        if usage_limit is not None:
                            times_used = promo_data.get("times_used", 0)
                            if times_used >= usage_limit:
                                logger.warning(f"User {message.from_user.id} tried to use a limit-reached promocode {promocode}.")
                                # Не применяем скидку, но продолжаем заказ
                                discount_percent = 0
                            else:
                                discount_percent = promo_data.get("discount", 0)
                        else:
                            discount_percent = promo_data.get("discount", 0)
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


async def _finalize_order(message: Message, user: User, state: FSMContext, bot: Bot, is_callback: bool = False):
    """Внутренняя функция для завершения заказа, сохранения и отправки уведомлений."""
    user_data = await state.get_data()
    cart = user_data.get('cart', {})
    items_price = user_data.get('items_price', 0)
    promocode = user_data.get('promocode')
    discount_percent = user_data.get('discount_percent', 0)
    delivery_cost = user_data.get('delivery_cost', 0)
    discount_amount = (items_price * discount_percent) / 100
    total_price = items_price - discount_amount + delivery_cost
    shipping_method = user_data.get('shipping_method', 'Не указан')
    address = user_data.get('address')

    # Формируем итоговый текст для пользователя
    response_text = "✅ <b>Спасибо за ваш заказ!</b>\n\nВы заказали:\n"
    for item_id, quantity in cart.items():
        # Используем новую функцию для поиска товара
        product = await get_product_by_id(item_id) or {"name": "Неизвестный товар", "price": 0}
        response_text += f"• {product['name']} x {quantity} шт. = {product['price'] * quantity} руб.\n"
    
    response_text += f"\nСтоимость товаров: {items_price} руб.\n"
    if discount_amount > 0:
        response_text += f"Скидка по промокоду '{promocode}': -{discount_amount:.2f} руб.\n"
    if delivery_cost > 0:
        response_text += f"Стоимость доставки: {delivery_cost} руб.\n"

    response_text += f"\n<b>Способ получения:</b> {shipping_method}"
    if address:
        response_text += f"\n<b>Адрес доставки:</b> {address}"
    response_text += f"\n<b>Итого к оплате: {total_price:.2f} руб.</b>"

    # Сохраняем заказ в "базу данных"
    order_details = {
        "cart": cart, "items_price": items_price, "promocode": promocode, 
        "discount_amount": discount_amount, "delivery_cost": delivery_cost,
        "total_price": total_price, "shipping_method": shipping_method
    }
    if address:
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

    # Отправляем подтверждение пользователю
    if is_callback:
        await message.edit_text(response_text)
    else:
        await message.answer(response_text)

    await state.clear()

    # Уведомляем администратора
    if ADMIN_ID:
        try:
            admin_text = f"🔔 <b>Новый заказ #{new_order['id']}!</b>\n\n<b>От:</b> {user.full_name} (ID: <code>{user.id}</code>)\n"
            admin_text += f"<b>Username:</b> @{user.username or 'не указан'}\n\n<b>Состав заказа:</b>\n"
            for item_id, quantity in cart.items():
                # Используем новую функцию для поиска товара
                product = await get_product_by_id(item_id) or {"name": "Неизвестный товар"}
                admin_text += f"• {product['name']} x {quantity} шт.\n"
            if discount_amount > 0:
                admin_text += f"\n<b>Промокод:</b> {promocode} (-{discount_amount:.2f} руб.)"
            if delivery_cost > 0:
                admin_text += f"\n<b>Доставка:</b> {delivery_cost} руб."
            admin_text += f"\n<b>Способ получения:</b> {shipping_method}"
            if address:
                admin_text += f"\n<b>Адрес доставки:</b> {address}"
            admin_text += f"\n<b>Итого: {total_price:.2f} руб.</b>"
            await bot.send_message(
                ADMIN_ID,
                admin_text,
                reply_markup=get_new_order_admin_keyboard()
            )
            logger.info(f"Admin {ADMIN_ID} has been notified about the new order from user {user.id}.")
        except Exception as e:
            logger.error(f"Failed to send notification to admin {ADMIN_ID}: {e}")


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