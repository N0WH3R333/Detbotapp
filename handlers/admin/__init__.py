import logging
from aiogram import Router, F

from config import ADMIN_IDS

logger = logging.getLogger(__name__)

admin_router = Router()

# Import routers from submodules
from . import base
from . import bookings
from . import stats
from . import orders
from . import clients
from . import block_management
from . import promocodes
from . import broadcast
from . import candidates
from . import info_cmds
from . import targeted_broadcast
from . import administration

admin_router.include_router(base.router)
admin_router.include_router(bookings.router)
admin_router.include_router(stats.router)
admin_router.include_router(orders.router)
admin_router.include_router(clients.router)
admin_router.include_router(block_management.router)
admin_router.include_router(promocodes.router)
admin_router.include_router(broadcast.router)
admin_router.include_router(candidates.router)
admin_router.include_router(info_cmds.router)
admin_router.include_router(targeted_broadcast.router)
admin_router.include_router(administration.router)

if ADMIN_IDS:
    admin_router.message.filter(F.from_user.id.in_(ADMIN_IDS))
    admin_router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))
    logger.info(f"Admin router configured for IDs: {ADMIN_IDS}")