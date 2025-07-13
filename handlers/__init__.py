from aiogram import Router

# Импортируем роутер админ-панели из под-пакета admin
from .admin import admin_router

# Импортируем роутеры для пользовательской части
from . import common
from . import booking
from . import webapp_shop      # <-- Вот он, наш новый магазин!
from . import group_management
from . import hiring

# Создаем главный роутер, который объединит все остальные
main_router = Router()

# Подключаем все роутеры к главному.
# Порядок подключения важен, если у вас есть пересекающиеся хэндлеры.
main_router.include_router(admin_router)
main_router.include_router(common.router)
main_router.include_router(booking.router)
main_router.include_router(webapp_shop.router)
main_router.include_router(group_management.router)
main_router.include_router(hiring.router)