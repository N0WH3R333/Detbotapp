import logging
import math

from aiogram import F, Router, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .states import AdminStates
from database.db import get_all_unique_users, update_user_full_name
from keyboards.admin_inline import (
    get_clients_list_keyboard, AdminClientPaginator, AdminEditClient,
    get_client_editing_keyboard, get_back_to_menu_keyboard, get_admin_keyboard
)

ADMIN_ITEMS_PER_PAGE = 5
logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_client_management")
async def client_management_start(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс управления клиентами, показывает первую страницу."""
    await state.clear()
    all_users_dict = await get_all_unique_users()
    # Преобразуем в список для пагинации и сортируем по ID
    all_users_list = sorted(
        [{'user_id': uid, **udata} for uid, udata in all_users_dict.items()],
        key=lambda x: x['user_id']
    )

    if not all_users_list:
        await callback.message.edit_text(
            "Пока нет ни одного клиента.",
            reply_markup=get_back_to_menu_keyboard("admin_back_to_main")
        )
        await callback.answer()
        return

    page = 0
    total_pages = math.ceil(len(all_users_list) / ADMIN_ITEMS_PER_PAGE)
    clients_on_page = all_users_list[0:ADMIN_ITEMS_PER_PAGE]

    # Сохраняем отсортированный список в FSM для пагинации
    await state.update_data(all_users_list=all_users_list)

    await callback.message.edit_text(
        "<b>Управление клиентами</b>\n\nВыберите клиента для редактирования:",
        reply_markup=get_clients_list_keyboard(clients_on_page, page, total_pages)
    )
    await callback.answer()


@router.callback_query(AdminClientPaginator.filter())
async def paginate_admin_clients(callback: CallbackQuery, callback_data: AdminClientPaginator, state: FSMContext):
    """Пагинация по списку клиентов."""
    page = callback_data.page + 1 if callback_data.action == "next" else callback_data.page - 1

    user_data = await state.get_data()
    all_users_list = user_data.get('all_users_list', [])

    if not all_users_list:
        await client_management_start(callback, state)
        return

    total_pages = math.ceil(len(all_users_list) / ADMIN_ITEMS_PER_PAGE)
    clients_on_page = all_users_list[page * ADMIN_ITEMS_PER_PAGE:(page + 1) * ADMIN_ITEMS_PER_PAGE]

    await callback.message.edit_text(
        "<b>Управление клиентами</b>\n\nВыберите клиента для редактирования:",
        reply_markup=get_clients_list_keyboard(clients_on_page, page, total_pages)
    )
    await callback.answer()


@router.callback_query(AdminEditClient.filter(F.action == "select"))
async def select_client_to_edit(callback: CallbackQuery, callback_data: AdminEditClient, state: FSMContext):
    """Показывает меню редактирования для выбранного клиента."""
    user_id = callback_data.user_id
    all_users = await get_all_unique_users()
    client_info = all_users.get(user_id)

    if not client_info:
        await callback.answer("Клиент не найден, список мог обновиться.", show_alert=True)
        await client_management_start(callback, state)
        return

    name = client_info.get('user_full_name', f"ID: {user_id}")
    username = client_info.get('user_username')
    display_name = f"{name}" + (f" (@{username})" if username else "")

    text = f"<b>Редактирование клиента:</b>\n{display_name}\n\nВыберите действие:"

    await callback.message.edit_text(
        text,
        reply_markup=get_client_editing_keyboard(
            user_id=user_id,
            user_full_name=name,
            back_callback="admin_client_management"
        )
    )
    await callback.answer()


@router.callback_query(AdminEditClient.filter(F.action == "edit_name"))
async def start_editing_client_name(callback: CallbackQuery, callback_data: AdminEditClient, state: FSMContext):
    """Начинает FSM для смены имени клиента."""
    await state.set_state(AdminStates.entering_new_client_name)
    await state.update_data(
        user_id_to_edit=callback_data.user_id,
        message_to_edit=callback.message.message_id
    )
    await callback.message.edit_text(
        "Введите новое имя для клиента:",
        reply_markup=get_back_to_menu_keyboard("admin_client_management")
    )
    await callback.answer()


@router.message(AdminStates.entering_new_client_name, F.text)
async def process_new_client_name(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает новое имя и обновляет данные."""
    new_name = message.text
    user_data = await state.get_data()
    user_id = user_data.get("user_id_to_edit")
    message_to_edit_id = user_data.get("message_to_edit")

    await message.delete()

    if not user_id or not message_to_edit_id:
        await state.clear()
        await bot.edit_message_text(
            "Произошла ошибка, данные для редактирования утеряны. Попробуйте снова.",
            chat_id=message.chat.id,
            message_id=message_to_edit_id
        )
        return

    success = await update_user_full_name(user_id, new_name)
    await state.clear()

    if success:
        text = f"✅ Имя для пользователя <code>{user_id}</code> успешно изменено на <b>{new_name}</b>."
    else:
        text = f"⚠️ Не удалось найти записи для пользователя <code>{user_id}</code> для обновления имени."

    await bot.edit_message_text(
        f"{text}\n\nВозврат в админ-панель.",
        chat_id=message.chat.id,
        message_id=message_to_edit_id,
        reply_markup=get_admin_keyboard()
    )