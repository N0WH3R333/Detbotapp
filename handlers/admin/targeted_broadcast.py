import logging
import re
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder

from keyboards.admin_inline import get_back_to_menu_keyboard
from utils.broadcast import send_broadcast
from database.db import get_user_ids_by_phone_numbers

logger = logging.getLogger(__name__)
router = Router()


class TargetedBroadcastStates(StatesGroup):
    getting_phone_numbers = State()
    getting_message = State()
    confirmation = State()


@router.callback_query(F.data == "admin_targeted_broadcast")
async def start_targeted_broadcast(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс адресной рассылки."""
    await state.clear()
    await state.set_state(TargetedBroadcastStates.getting_phone_numbers)
    await callback.message.edit_text(
        "<b>🎯 Адресная рассылка по номерам телефонов</b>\n\n"
        "Отправьте список номеров телефонов. Каждый номер с новой строки или через запятую/пробел.\n\n"
        "<i>Бот сможет отправить сообщение только тем пользователям, которые ранее взаимодействовали с ботом и делились своим контактом.</i>",
        reply_markup=get_back_to_menu_keyboard("admin_back_to_main")
    )
    await callback.answer()


@router.message(TargetedBroadcastStates.getting_phone_numbers, F.text)
async def get_phone_numbers(message: Message, state: FSMContext):
    """Получает и обрабатывает номера телефонов."""
    # Разделяем введенный текст по пробелам, запятым, точкам с запятой и переносам строк
    delimiters = r'[\s,;\n]+'
    phone_numbers_raw = re.split(delimiters, message.text.strip())

    # Очищаем каждый номер, оставляя только цифры
    cleaned_numbers = [re.sub(r'\D', '', num) for num in phone_numbers_raw if num]
    cleaned_numbers = list(set(num for num in cleaned_numbers if num)) # Уникальные номера

    if not cleaned_numbers:
        await message.answer(
            "Не удалось найти ни одного номера телефона в вашем сообщении. "
            "Пожалуйста, отправьте номера, разделенные пробелом, запятой или с новой строки.",
            reply_markup=get_back_to_menu_keyboard("admin_back_to_main")
        )
        return

    found_users_map = await get_user_ids_by_phone_numbers(cleaned_numbers)
    found_user_ids = list(found_users_map.values())

    # Для отчета нам нужны не найденные номера в том виде, как их ввели (очищенном)
    found_db_numbers = {re.sub(r'\D', '', p) for p in found_users_map.keys()}
    not_found_numbers = [p for p in cleaned_numbers if p not in found_db_numbers]

    await state.update_data(
        target_user_ids=found_user_ids,
        not_found_numbers=not_found_numbers
    )

    if not found_user_ids:
        await message.answer(
            f"❌ Ни один из {len(cleaned_numbers)} введенных номеров не найден в базе данных бота. Рассылка невозможна.",
            reply_markup=get_back_to_menu_keyboard("admin_back_to_main")
        )
        await state.clear()
        return

    await state.set_state(TargetedBroadcastStates.getting_message)
    await message.answer(
        f"✅ Найдено пользователей: <b>{len(found_user_ids)}</b>\n"
        f"🤷‍♂️ Не найдено в базе: <b>{len(not_found_numbers)}</b>\n\n"
        "Теперь отправьте или перешлите сюда сообщение, которое вы хотите разослать этим пользователям.",
        reply_markup=get_back_to_menu_keyboard("admin_targeted_broadcast")
    )


@router.message(TargetedBroadcastStates.getting_message)
async def get_targeted_broadcast_message(message: Message, state: FSMContext, bot: Bot):
    """Получает сообщение для рассылки и показывает предпросмотр."""
    await state.update_data(message_id=message.message_id, from_chat_id=message.chat.id)

    await message.answer("Вот так будет выглядеть ваше сообщение для рассылки:")
    await bot.copy_message(chat_id=message.chat.id, from_chat_id=message.chat.id, message_id=message.message_id)

    await state.set_state(TargetedBroadcastStates.confirmation)
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Отправить найденным", callback_data="targeted_broadcast_send")
    builder.button(text="❌ Отменить", callback_data="targeted_broadcast_cancel")
    await message.answer("Отправляем это сообщение?", reply_markup=builder.as_markup())


@router.callback_query(F.data == "targeted_broadcast_send", TargetedBroadcastStates.confirmation)
async def confirm_and_send_targeted(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Подтверждает и запускает адресную рассылку."""
    data = await state.get_data()
    target_user_ids = data.get('target_user_ids', [])
    not_found_numbers = data.get('not_found_numbers', [])
    await state.clear()

    await callback.message.edit_text("⏳ Начинаю адресную рассылку...")
    successful, failed = await send_broadcast(bot=bot, user_ids=target_user_ids, content=data)

    report_text = (
        f"✅ Адресная рассылка завершена!\n\n"
        f"📬 Успешно отправлено: <b>{successful}</b>\n"
        f"❌ Не удалось отправить: <b>{failed}</b>\n\n"
        f"🤷‍♂️ Номера не найдены в базе ({len(not_found_numbers)} шт.)"
    )
    await callback.message.answer(report_text)
    await callback.answer()


@router.callback_query(F.data == "targeted_broadcast_cancel", StateFilter(TargetedBroadcastStates))
async def cancel_targeted_process(callback: CallbackQuery, state: FSMContext):
    """Отменяет процесс адресной рассылки."""
    await state.clear()
    await callback.message.edit_text("Адресная рассылка отменена.")
    await callback.answer()