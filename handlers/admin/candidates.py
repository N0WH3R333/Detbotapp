import logging
import math

from aiogram import F, Router, Bot, types
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.db import get_all_candidates, delete_candidate_in_db
from keyboards.admin_inline import (
    get_candidates_list_keyboard, AdminManageCandidate, AdminCandidatesPaginator,
    get_back_to_menu_keyboard
)
from .states import AdminStates

ADMIN_ITEMS_PER_PAGE = 5
logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_candidates_management")
async def candidates_management_start(callback: CallbackQuery, state: FSMContext):
    """Показывает первую страницу кандидатов."""
    await state.clear()
    all_candidates = sorted(await get_all_candidates(), key=lambda x: x['id'], reverse=True)

    if not all_candidates:
        await callback.message.edit_text(
            "Новых откликов на вакансии нет.",
            reply_markup=get_back_to_menu_keyboard("admin_back_to_main")
        )
        await callback.answer()
        return

    await state.update_data(all_candidates=all_candidates)

    page = 0
    total_pages = math.ceil(len(all_candidates) / ADMIN_ITEMS_PER_PAGE)
    candidates_on_page = all_candidates[0:ADMIN_ITEMS_PER_PAGE]

    await callback.message.edit_text(
        "📬 <b>Отклики на вакансии</b>\n\nВыберите отклик для просмотра:",
        reply_markup=get_candidates_list_keyboard(candidates_on_page, page, total_pages)
    )
    await callback.answer()


@router.callback_query(AdminCandidatesPaginator.filter())
async def paginate_admin_candidates(callback: CallbackQuery, callback_data: AdminCandidatesPaginator, state: FSMContext):
    """Пагинация по списку кандидатов."""
    page = callback_data.page
    if callback_data.action == "next":
        page += 1
    elif callback_data.action == "prev":
        page -= 1

    data = await state.get_data()
    all_candidates = data.get('all_candidates', [])

    if not all_candidates:
        await candidates_management_start(callback, state)
        return

    total_pages = math.ceil(len(all_candidates) / ADMIN_ITEMS_PER_PAGE)
    candidates_on_page = all_candidates[page * ADMIN_ITEMS_PER_PAGE:(page + 1) * ADMIN_ITEMS_PER_PAGE]

    await callback.message.edit_text(
        "📬 <b>Отклики на вакансии</b>\n\nВыберите отклик для просмотра:",
        reply_markup=get_candidates_list_keyboard(candidates_on_page, page, total_pages)
    )
    await callback.answer()


@router.callback_query(AdminManageCandidate.filter(F.action == "view"))
async def view_candidate(callback: CallbackQuery, callback_data: AdminManageCandidate, state: FSMContext):
    """Показывает полную информацию об отклике кандидата."""
    candidate_id = callback_data.candidate_id
    page = callback_data.page

    data = await state.get_data()
    all_candidates = data.get('all_candidates', await get_all_candidates())
    candidate = next((c for c in all_candidates if c.get('id') == candidate_id), None)

    if not candidate:
        await callback.answer("Отклик не найден. Возможно, он был удален.", show_alert=True)
        return

    text = (
        f"<b>Отклик #{candidate['id']} от {candidate['received_at']}</b>\n\n"
        f"<b>Кандидат:</b> {candidate['user_full_name']}\n"
        f"<b>ID:</b> <code>{candidate['user_id']}</code>\n"
        f"<b>Username:</b> @{candidate.get('user_username') or 'не указан'}\n\n"
        f"<b>Сообщение:</b>\n<pre>{candidate.get('message_text', 'Нет текста.')}</pre>"
    )
    if candidate.get('file_id'):
        text += f"\n\n📎 <b>Прикреплен файл:</b> {candidate.get('file_name', 'файл')}"

    builder = InlineKeyboardBuilder()
    if candidate.get('file_id'):
        builder.button(text="📥 Скачать файл", callback_data=AdminManageCandidate(action="get_file", candidate_id=candidate_id, page=page).pack())
    builder.button(text="🗑️ Удалить отклик", callback_data=AdminManageCandidate(action="delete", candidate_id=candidate_id, page=page).pack())
    builder.button(text="⬅️ Назад к списку", callback_data=AdminManageCandidate(action="back_list", candidate_id=0, page=page).pack())
    builder.adjust(1)

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(AdminManageCandidate.filter(F.action == "get_file"))
async def get_candidate_file(callback: CallbackQuery, callback_data: AdminManageCandidate, bot: Bot, state: FSMContext):
    """Отправляет прикрепленный файл админу."""
    candidate_id = callback_data.candidate_id
    data = await state.get_data()
    all_candidates = data.get('all_candidates', await get_all_candidates())
    candidate = next((c for c in all_candidates if c.get('id') == candidate_id), None)

    if candidate and candidate.get('file_id'):
        await callback.answer("Отправляю файл...")
        await bot.send_document(
            chat_id=callback.from_user.id,
            document=candidate['file_id'],
            caption=f"Файл от кандидата #{candidate_id} ({candidate['user_full_name']})"
        )
    else:
        await callback.answer("Файл не найден.", show_alert=True)


@router.callback_query(AdminManageCandidate.filter(F.action == "delete"))
async def delete_candidate(callback: CallbackQuery, callback_data: AdminManageCandidate, state: FSMContext):
    """Удаляет кандидата и обновляет список."""
    candidate_id = callback_data.candidate_id
    deleted_candidate = await delete_candidate_in_db(candidate_id)

    if not deleted_candidate:
        await callback.answer("Не удалось удалить отклик.", show_alert=True)
        return

    await callback.answer(f"Отклик #{candidate_id} удален.", show_alert=False)
    await candidates_management_start(callback, state)


@router.callback_query(AdminManageCandidate.filter(F.action == "back_list"))
async def back_to_candidates_list(callback: CallbackQuery, callback_data: AdminManageCandidate, state: FSMContext):
    """Возвращает к списку кандидатов на нужной странице."""
    await paginate_admin_candidates(callback, AdminCandidatesPaginator(action="noop", page=callback_data.page), state)