from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_services_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора основной услуги."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✨ Полировка кузова", callback_data="service:polishing")
    builder.button(text="🛡️ Керамика", callback_data="service:ceramics")
    builder.button(text="🛋️ Химчистка", callback_data="service:dry_cleaning")
    builder.button(text="🎨 Оклейка кузова", callback_data="service:wrapping")
    builder.button(text="💧 Трехфазная мойка", callback_data="service:washing")
    builder.button(text="🔍 Полировка стекол", callback_data="service:glass_polishing")
    builder.adjust(1)
    return builder.as_markup()

def get_car_size_keyboard(service_prefix: str) -> InlineKeyboardMarkup:
    """Клавиатура для выбора размера кузова."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🚗 Малый кузов", callback_data=f"car_size:{service_prefix}:small")
    builder.button(text="🚙 Средний кузов", callback_data=f"car_size:{service_prefix}:medium")
    builder.button(text="🚚 Большой кузов", callback_data=f"car_size:{service_prefix}:large")
    builder.button(text="⬅️ Назад", callback_data="back:main_services")
    builder.adjust(1)
    return builder.as_markup()

def get_polishing_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора типа полировки."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✨ Легкая полировка", callback_data="service_type:light_polishing")
    builder.button(text="💎 Глубокая полировка", callback_data="service_type:deep_polishing")
    builder.button(text="💰 Предпродажная полировка", callback_data="service_type:presale_polishing")
    builder.button(text="⬅️ Назад", callback_data="back:car_size:polishing")
    builder.adjust(1)
    return builder.as_markup()

def get_ceramics_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора типа керамики."""
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Предпродажная", callback_data="service_type:presale_ceramics")
    builder.button(text="🛡️ Средняя", callback_data="service_type:medium_ceramics")
    builder.button(text="💎 Длительная", callback_data="service_type:long_ceramics")
    builder.button(text="⬅️ Назад", callback_data="back:car_size:ceramics")
    builder.adjust(1)
    return builder.as_markup()

def get_wrapping_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора типа оклейки."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Полная оклейка", callback_data="service_type:full_wrapping")
    builder.button(text="Локальная оклейка", callback_data="service_type:local_wrapping")
    builder.button(text="⬅️ Назад", callback_data="back:car_size:wrapping")
    builder.adjust(1)
    return builder.as_markup()

def get_dry_cleaning_next_step_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура-прокладка для химчистки."""
    builder = InlineKeyboardBuilder()
    builder.button(text="➡️ Тип салона", callback_data="dry_cleaning:select_interior")
    builder.button(text="⬅️ Назад", callback_data="back:car_size:dry_cleaning")
    builder.adjust(1)
    return builder.as_markup()

def get_interior_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора типа салона."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🧵 Ткань", callback_data="interior_type:fabric")
    builder.button(text="🛋️ Кожа", callback_data="interior_type:leather")
    builder.button(text="⚜️ Алькантара", callback_data="interior_type:alcantara")
    builder.button(text="🔄 Комбинированный", callback_data="interior_type:combined")
    builder.button(text="⬅️ Назад", callback_data="back:to_dc_next_step")
    builder.adjust(1)
    return builder.as_markup()

def get_dirt_level_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора степени загрязнения."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🧼 Легкая", callback_data="dirt_level:light")
    builder.button(text="🧽 Средняя", callback_data="dirt_level:medium")
    builder.button(text="💥 Сильная", callback_data="dirt_level:strong")
    builder.button(text="⬅️ Назад", callback_data="back:interior_type")
    builder.adjust(1)
    return builder.as_markup()

def get_promocode_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для ввода промокода с кнопкой 'Пропустить'."""
    builder = InlineKeyboardBuilder()
    builder.button(text="➡️ Пропустить", callback_data="promo:skip")
    return builder.as_markup()

def get_comment_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для пропуска ввода комментария."""
    builder = InlineKeyboardBuilder()
    builder.button(text="➡️ Далее / Пропустить", callback_data="comment:skip")
    builder.adjust(1)
    return builder.as_markup()