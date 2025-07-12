import logging

from aiogram import F, Router, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.db import block_user, unblock_user, get_blocked_users
from keyboards.admin_inline import get_block_management_keyboard, get_back_to_menu_keyboard
from .states import AdminStates

logger = logging.getLogger(__name__)
router = Router()


async def _process_fsm_input_and_edit(
    message: Message, state: FSMContext, bot: Bot,
    processing_func, success_markup
):
    """Универсальный обработчик для FSM: удаляет сообщение, обрабатывает, редактирует исходное."""
    data = await state.get_data()
    message_to_edit_id = data.get("message_to_edit")

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except TelegramBadRequest:
        logger.warning(f"Could not delete user message {message.message_id}")

    text = await processing_func(message.text)

    await state.clear()
    final_text = f"{text}\n\nВыберите следующее действие:"

    if message_to_edit_id:
        try:
            await bot.edit_message_text(
                text=final_text,
                chat_id=message.chat.id,
                message_id=message_to_edit_id,
                reply_markup=success_markup
            )
        except TelegramBadRequest:
            # Если не удалось отредактировать (например, сообщение слишком старое), отправляем новое
            await bot.send_message(message.chat.id, final_text, reply_markup=success_markup)
    else:
        await bot.send_message(message.chat.id, final_text, reply_markup=success_markup)


@router.callback_query(F.data == "admin_block_management")
async def block_management(callback: CallbackQuery):
    """Показывает меню управления блокировками."""
    await callback.message.edit_text(
        "Выберите действие:",
        reply_markup=get_block_management_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_block_user")
async def start_blocking_user(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс блокировки пользователя."""
    await state.set_state(AdminStates.entering_user_id_to_block)
    await state.update_data(message_to_edit=callback.message.message_id)
    await callback.message.edit_text(
        "Введите ID пользователя для блокировки:",
        reply_markup=get_back_to_menu_keyboard("admin_block_management")
    )
    await callback.answer()


@router.message(AdminStates.entering_user_id_to_block, F.text)
async def process_blocking_user(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает введенный ID для блокировки."""
    async def _processor(text: str):
        try:
            user_id = int(text)
            await block_user(user_id)
            return f"✅ Пользователь <code>{user_id}</code> заблокирован."
        except ValueError:
            return "⚠️ Неверный формат ID. Пожалуйста, введите число."
        except Exception as e:
            logger.error(f"Error blocking user: {e}")
            return "❌ Произошла ошибка при блокировке."

    await _process_fsm_input_and_edit(
        message, state, bot, _processor, get_block_management_keyboard()
    )


@router.callback_query(F.data == "admin_unblock_user")
async def start_unblocking_user(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс разблокировки пользователя."""
    await state.set_state(AdminStates.entering_user_id_to_unblock)
    await state.update_data(message_to_edit=callback.message.message_id)
    await callback.message.edit_text(
        "Введите ID пользователя для разблокировки:",
        reply_markup=get_back_to_menu_keyboard("admin_block_management")
    )
    await callback.answer()


@router.message(AdminStates.entering_user_id_to_unblock, F.text)
async def process_unblocking_user(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает введенный ID для разблокировки."""
    async def _processor(text: str):
        try:
            user_id = int(text)
            await unblock_user(user_id)
            return f"✅ Пользователь <code>{user_id}</code> разблокирован."
        except ValueError:
            return "⚠️ Неверный формат ID. Пожалуйста, введите число."
        except Exception as e:
            logger.error(f"Error unblocking user: {e}")
            return "❌ Произошла ошибка при разблокировке."

    await _process_fsm_input_and_edit(
        message, state, bot, _processor, get_block_management_keyboard()
    )


@router.callback_query(F.data == "admin_show_blocked")
async def show_blocked_users(callback: CallbackQuery):
    """Показывает список заблокированных пользователей."""
    blocked_users = await get_blocked_users()
    if not blocked_users:
        text = "Список заблокированных пользователей пуст."
    else:
        text = "<b>Заблокированные пользователи:</b>\n\n"
        text += "\n".join(f"• <code>{user_id}</code>" for user_id in blocked_users)

    await callback.message.edit_text(
        text,
        reply_markup=get_back_to_menu_keyboard("admin_block_management")
    )
    await callback.answer()