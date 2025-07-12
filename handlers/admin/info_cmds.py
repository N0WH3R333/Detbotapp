import json
import logging
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message, InputMediaPhoto, InputMediaVideo
from aiogram.filters.command import CommandObject
from database.db import get_booking_by_id, update_user_note
from utils.constants import ALL_NAMES

logger = logging.getLogger(__name__)
router = Router()

def format_booking_details_for_admin(booking: dict) -> str:
    """Форматирует детальную информацию о записи для админа."""
    # details_json из базы приходит как строка, ее нужно распарсить
    details_raw = booking.get('details_json')
    details = {}
    if isinstance(details_raw, str):
        details = json.loads(details_raw)
    elif isinstance(details_raw, dict):
        details = details_raw
    
    service_details_lines = []
    if car_size := details.get('car_size'):
        service_details_lines.append(f"  - Размер: {ALL_NAMES.get(car_size, car_size)}")
    if service_type := details.get('service_type'):
        service_details_lines.append(f"  - Тип: {ALL_NAMES.get(service_type, service_type)}")
    if interior_type := details.get('interior_type'):
        service_details_lines.append(f"  - Салон: {ALL_NAMES.get(interior_type, interior_type)}")
    if dirt_level := details.get('dirt_level'):
        service_details_lines.append(f"  - Загрязнение: {ALL_NAMES.get(dirt_level, dirt_level)}")
    
    service_details_str = "\n".join(service_details_lines)
    if service_details_str:
        service_details_str = "\n" + service_details_str

    text = (
        f"📄 <b>Детали записи #{booking['id']}</b>\n"
        f"<b>Статус:</b> {booking.get('status', 'N/A')}\n\n"
        f"🗓️ <b>Дата:</b> {booking.get('date')} в {booking.get('time')}\n\n"
        f"<b>Услуга:</b> {booking.get('service_name', 'Не указана')}{service_details_str}\n\n"
        f"💰 <b>Финансы:</b>\n"
        f"  - Стоимость: {booking.get('price_rub', 0)} руб.\n"
        f"  - Скидка: {booking.get('discount_rub', 0)} руб.\n"
        f"  - Промокод: {booking.get('promocode') or 'Нет'}\n\n"
        f"👤 <b>Клиент:</b>\n"
        f"  - Имя: {booking.get('user_full_name', 'N/A')}\n"
        f"  - ID: <code>{booking.get('user_id')}</code>\n"
        f"  - Username: @{booking.get('user_username') or 'скрыт'}\n"
        f"  - Заблокирован: {'Да' if booking.get('user_is_blocked') else 'Нет'}\n"
        f"  - 📝 <b>Заметка:</b>\n<pre>{booking.get('user_internal_note') or 'Пусто'}</pre>\n\n"
    )
    if comment := booking.get('comment'):
        text += f"<b>Комментарий клиента:</b>\n<pre>{comment}</pre>\n"
    
    return text

@router.message(Command("binfo"))
async def get_booking_info(message: Message, command: CommandObject, bot: Bot):
    """
    Отправляет админу полную информацию о записи по её ID, включая медиа.
    Использование: /binfo <booking_id>
    """
    if not command.args or not command.args.isdigit():
        await message.answer("Пожалуйста, укажите ID записи. Пример: <code>/binfo 123</code>")
        return

    booking_id = int(command.args)
    booking = await get_booking_by_id(booking_id)

    if not booking:
        await message.answer(f"Запись с ID <code>{booking_id}</code> не найдена.")
        return

    info_text = format_booking_details_for_admin(booking)
    
    media_files = booking.get("media_files", [])
    if not media_files:
        await message.answer(info_text)
    elif len(media_files) == 1:
        media = media_files[0]
        if media['type'] == 'photo':
            await bot.send_photo(message.chat.id, photo=media['file_id'], caption=info_text)
        else:
            await bot.send_video(message.chat.id, video=media['file_id'], caption=info_text)
    else:
        await message.answer(info_text)
        media_group = [
            InputMediaPhoto(media=m['file_id']) if m['type'] == 'photo'
            else InputMediaVideo(media=m['file_id'])
            for m in media_files
        ]
        await bot.send_media_group(message.chat.id, media=media_group)

@router.message(Command("note"))
async def add_user_note(message: Message, command: CommandObject):
    """
    Добавляет или обновляет внутреннюю заметку о пользователе.
    Использование: /note <user_id> <текст заметки>
    Чтобы удалить заметку: /note <user_id>
    """
    if not command.args:
        await message.answer(
            "<b>Как использовать команду:</b>\n"
            "<code>/note &lt;ID пользователя&gt; &lt;текст заметки&gt;</code> - добавить/изменить заметку.\n"
            "<code>/note &lt;ID пользователя&gt;</code> - удалить заметку."
        )
        return

    args = command.args.split(maxsplit=1)
    user_id_str = args[0]
    note_text = args[1] if len(args) > 1 else ""

    if not user_id_str.isdigit():
        await message.answer("ID пользователя должен быть числом.")
        return
    
    user_id = int(user_id_str)
    success = await update_user_note(user_id, note_text)

    if success:
        await message.answer(f"✅ Заметка для пользователя <code>{user_id}</code> успешно {'обновлена' if note_text else 'удалена'}.")
    else:
        await message.answer(f"⚠️ Не удалось обновить заметку для пользователя <code>{user_id}</code>. Возможно, такого пользователя нет в базе.")