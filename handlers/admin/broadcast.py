import asyncio
import logging

from aiogram import F, Router, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message

from database.db import get_all_unique_user_ids
from keyboards.admin_inline import get_back_to_menu_keyboard, get_broadcast_confirmation_keyboard, get_admin_keyboard

logger = logging.getLogger(__name__)
router = Router()


class BroadcastStates(StatesGroup):
    entering_broadcast_message = State()
    confirming_broadcast = State()


@router.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс создания рассылки."""
    await state.set_state(BroadcastStates.entering_broadcast_message)
    await callback.message.edit_text(
        "Перешлите или отправьте сообщение, которое вы хотите разослать всем пользователям.",
        reply_markup=get_back_to_menu_keyboard("admin_back_to_main")
    )
    await callback.answer()


@router.message(BroadcastStates.entering_broadcast_message)
async def broadcast_message_received(message: Message, state: FSMContext):
    """Получает сообщение (любого типа) для рассылки и просит подтверждения."""
    await state.update_data(broadcast_chat_id=message.chat.id, broadcast_message_id=message.message_id)
    await message.answer(
        "Вы уверены, что хотите отправить это сообщение всем пользователям?",
        reply_markup=get_broadcast_confirmation_keyboard()
    )
    await state.set_state(BroadcastStates.confirming_broadcast)


@router.callback_query(BroadcastStates.confirming_broadcast, F.data == "admin_broadcast_confirm")
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Подтверждает и запускает рассылку."""
    data = await state.get_data()
    chat_id = data.get('broadcast_chat_id')
    message_id = data.get('broadcast_message_id')
    await state.clear()

    if not chat_id or not message_id:
        await callback.message.edit_text("Произошла ошибка, данные для рассылки утеряны. Попробуйте снова.", reply_markup=get_admin_keyboard())
        return

    user_ids = await get_all_unique_user_ids()
    if not user_ids:
        await callback.message.edit_text("Не найдено ни одного пользователя для рассылки.", reply_markup=get_admin_keyboard())
        return

    await callback.message.edit_text(f"Начинаю рассылку для {len(user_ids)} пользователей...")
    success_count, fail_count = 0, 0
    for user_id in user_ids:
        try:
            await bot.copy_message(chat_id=user_id, from_chat_id=chat_id, message_id=message_id)
            success_count += 1
        except Exception as e:
            fail_count += 1
            logger.error(f"Failed to send broadcast message to {user_id}. Error: {e}")
        await asyncio.sleep(0.1)

    report_text = f"✅ <b>Рассылка завершена!</b>\n\nУспешно отправлено: {success_count}\nНе удалось отправить: {fail_count}"
    await callback.message.edit_text(report_text, reply_markup=get_admin_keyboard())


@router.callback_query(F.data == "admin_broadcast_cancel", BroadcastStates.confirming_broadcast)
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    """Отменяет рассылку."""
    await state.clear()
    await callback.message.edit_text("Рассылка отменена.", reply_markup=get_admin_keyboard())
    await callback.answer()