SERVICE_NAMES = {
    # Services
    "polishing": "✨ Полировка кузова",
    "ceramics": "🛡️ Керамика",
    "dry_cleaning": "🛋️ Химчистка",
    "wrapping": "🎨 Оклейка кузова",
    "washing": "💧 Трехфазная мойка",
    "glass_polishing": "🔍 Полировка стекол",
}

CAR_SIZE_NAMES = {
    "small": "🚗 Малый кузов",
    "medium": "🚙 Средний кузов",
    "large": "🚚 Большой кузов",
}

POLISHING_TYPE_NAMES = {
    "light_polishing": "✨ Легкая полировка",
    "deep_polishing": "💎 Глубокая полировка",
    "presale_polishing": "💰 Предпродажная полировка",
}

CERAMICS_TYPE_NAMES = {
    "presale_ceramics": "💰 Предпродажная",
    "medium_ceramics": "🛡️ Средняя",
    "long_ceramics": "💎 Длительная",
}

WRAPPING_TYPE_NAMES = {
    "full_wrapping": "Полная оклейка",
    "local_wrapping": "Локальная оклейка",
}

INTERIOR_TYPE_NAMES = {
    "fabric": "🧵 Ткань",
    "leather": "🛋️ Кожа",
    "alcantara": "⚜️ Алькантара",
    "combined": "🔄 Комбинированный",
}

DIRT_LEVEL_NAMES = {
    "light": "🧼 Легкая",
    "medium": "🧽 Средняя",
    "strong": "💥 Сильная",
}

# Списки ключей, которые используются в bot.py
CAR_SIZES = list(CAR_SIZE_NAMES.keys())
POLISHING_TYPES = list(POLISHING_TYPE_NAMES.keys())
CERAMICS_TYPES = list(CERAMICS_TYPE_NAMES.keys())
WRAPPING_TYPES = list(WRAPPING_TYPE_NAMES.keys())
INTERIOR_TYPES = list(INTERIOR_TYPE_NAMES.keys())
DIRT_LEVELS = list(DIRT_LEVEL_NAMES.keys())

# Единый список рабочих часов для записи
WORKING_HOURS = [
    "08:00", "09:00", "10:00", "11:00", "12:00", "13:00",
    "14:00", "15:00", "16:00", "17:00", "18:00"
    # Последняя запись на 18:00, так как работа до 19:00
]