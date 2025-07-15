import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter

from keyboards.admin_inline import get_broadcast_options_keyboard, get_back_to_menu_keyboard, get_button_markup
from utils.broadcast import send_broadcast
from database.db import get_all_unique_user_ids

logger = logging.getLogger(__name__)
router = Router()

# TODO: Добавьте фильтр, если рассылку могут делать не все админы, а например, только SUPER_ADMIN
# from middlewares.admin_filter import IsSuperAdmin
# router.message.filter(IsSuperAdmin())
# router.callback_query.filter(IsSuperAdmin())

class BroadcastStates(StatesGroup):
    getting_message = State()
    confirmation = State()
    getting_button_text = State()
    getting_button_callback = State()


@router.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс создания рассылки."""
    await state.clear()
    await state.set_state(BroadcastStates.getting_message)
    await callback.message.edit_text(
        "Отправьте или перешлите сюда сообщение, которое вы хотите разослать всем пользователям.",
        reply_markup=get_back_to_menu_keyboard("admin_back_to_main")
    )
    await callback.answer()


@router.message(BroadcastStates.getting_message)
async def get_broadcast_message(message: Message, state: FSMContext, bot: Bot):
    """Получает сообщение для рассылки и показывает предпросмотр."""
    await state.update_data(
        message_id=message.message_id,
        from_chat_id=message.chat.id,
        button=None
    )
    
    await message.answer("Вот так будет выглядеть ваше сообщение для рассылки:")
    await bot.copy_message(chat_id=message.chat.id, from_chat_id=message.chat.id, message_id=message.message_id)

    await state.set_state(BroadcastStates.confirmation)
    await message.answer(
        "Что делаем дальше?",
        reply_markup=get_broadcast_options_keyboard()
    )


@router.callback_query(F.data == "broadcast_send", BroadcastStates.confirmation)
async def confirm_and_send(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()

    await callback.message.edit_text("⏳ Начинаю рассылку... Это может занять некоторое время.")
    
    # Получаем ID всех пользователей для массовой рассылки
    user_ids = await get_all_unique_user_ids()
    successful, failed = await send_broadcast(bot=bot, user_ids=list(user_ids), content=data)
    
    await callback.message.answer(
        f"✅ Рассылка завершена!\n\n"
        f"📬 Успешно отправлено: {successful}\n"
        f"❌ Не удалось отправить: {failed}"
    )
    await callback.answer()


@router.callback_query(F.data == "broadcast_add_button", BroadcastStates.confirmation)
async def add_button_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastStates.getting_button_text)
    await callback.message.edit_text(
        "Введите текст для кнопки.",
        reply_markup=get_back_to_menu_keyboard("broadcast_cancel") # Общая отмена
    )
    await callback.answer()


@router.message(BroadcastStates.getting_button_text)
async def get_button_text(message: Message, state: FSMContext):
    await state.update_data(button_text=message.text)
    await state.set_state(BroadcastStates.getting_button_callback)
    await message.answer(
        "Отлично. Теперь введите callback-данные для кнопки (латинские буквы, цифры, _). "
        "Это уникальный идентификатор, который будет срабатывать при нажатии.",
        reply_markup=get_back_to_menu_keyboard("broadcast_cancel")
    )


@router.message(BroadcastStates.getting_button_callback)
async def get_button_callback(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    button_data = {"text": data['button_text'], "callback_data": message.text}
    await state.update_data(button=button_data)
    
    await message.answer("Кнопка добавлена! Вот обновленный предпросмотр:")
    await bot.copy_message(
        chat_id=message.chat.id, from_chat_id=data['from_chat_id'],
        message_id=data['message_id'], reply_markup=get_button_markup(button_data)
    )

    await state.set_state(BroadcastStates.confirmation)
    await message.answer("Что делаем дальше?", reply_markup=get_broadcast_options_keyboard())


@router.callback_query(F.data == "broadcast_cancel", StateFilter(BroadcastStates))
async def cancel_process(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Рассылка отменена.")
    await callback.answer()