import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.db import add_admin, get_admin_list, remove_admin
from keyboards.admin_inline import get_admin_management_keyboard, get_admins_list_keyboard, get_back_to_menu_keyboard
from middlewares.admin_filter import IsSuperAdmin
from .states import AdminStates
from config import SUPER_ADMIN_ID

logger = logging.getLogger(__name__)
router = Router()

# Применяем фильтр ко всему роутеру, чтобы защитить все его обработчики
router.message.filter(IsSuperAdmin())
router.callback_query.filter(IsSuperAdmin())


@router.callback_query(F.data == "admin_manage_admins")
async def manage_admins_menu(callback: CallbackQuery):
    """Показывает меню управления администраторами."""
    await callback.message.edit_text(
        "👑 <b>Раздел управления администрацией</b>\n\n"
        "Здесь вы можете добавлять и удалять администраторов.",
        reply_markup=get_admin_management_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_remove_admin_start")
async def list_admins(callback: CallbackQuery):
    """Показывает список администраторов с кнопками для удаления."""
    admins = await get_admin_list()
    super_admin_info = f"👑 <b>Супер-админ:</b> <code>{SUPER_ADMIN_ID}</code> (неизменяемый)\n"

    if not admins:
        text = super_admin_info + "\nОбычные администраторы отсутствуют."
    else:
        text = super_admin_info + "\n<b>Администраторы:</b>\n"
        admin_lines = []
        for admin in admins:
            username = f"(@{admin['username']})" if admin['username'] else ""
            admin_lines.append(f"• {admin['full_name']} {username} (<code>{admin['user_id']}</code>)")
        text += "\n".join(admin_lines)

    await callback.message.edit_text(
        text,
        reply_markup=get_admins_list_keyboard(admins)
    )
    await callback.answer()


@router.callback_query(F.data == "admin_add_admin")
async def add_admin_start(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс добавления нового администратора."""
    await state.set_state(AdminStates.entering_add_admin_id)
    await callback.message.edit_text(
        "Введите ID пользователя, которого вы хотите назначить администратором.\n\n"
        "Пользователь должен хотя бы раз запустить бота, чтобы его можно было добавить.",
        reply_markup=get_back_to_menu_keyboard("admin_manage_admins")
    )
    await callback.answer()


@router.message(AdminStates.entering_add_admin_id, F.text)
async def add_admin_process(message: Message, state: FSMContext):
    """Обрабатывает введенный ID и назначает администратора."""
    if not message.text.isdigit():
        await message.answer("ID должен быть числом. Попробуйте еще раз.")
        return

    user_id_to_add = int(message.text)
    if user_id_to_add == SUPER_ADMIN_ID:
        # Если пытаются добавить супер-админа, сообщаем об этом и выходим из состояния
        await message.answer("Этот пользователь уже является супер-администратором. Возвращаю в меню.")
        await state.clear()
        return

    success = await add_admin(user_id_to_add)
    await state.clear()

    if success:
        text = f"✅ Пользователь с ID <code>{user_id_to_add}</code> успешно назначен администратором."
    else:
        text = (f"❌ Не удалось назначить администратора с ID <code>{user_id_to_add}</code>. "
                f"Убедитесь, что пользователь существует и запустил бота.")

    await message.answer(text, reply_markup=get_admin_management_keyboard())


@router.callback_query(F.data.startswith("admin_remove_admin_"))
async def remove_admin_process(callback: CallbackQuery):
    """Обрабатывает удаление администратора по нажатию на кнопку."""
    user_id_to_remove = int(callback.data.split("_")[-1])
    success = await remove_admin(user_id_to_remove)
    if success:
        await callback.answer(f"Администратор {user_id_to_remove} удален.", show_alert=True)
    else:
        await callback.answer("Не удалось удалить администратора.", show_alert=True)

    # Обновляем список админов
    await list_admins(callback)