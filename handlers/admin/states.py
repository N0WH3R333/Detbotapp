from aiogram.fsm.state import StatesGroup, State

class AdminStates(StatesGroup):
    # Block management
    entering_user_id_to_block = State()
    entering_user_id_to_unblock = State()
    # Order management
    entering_order_id_to_cancel = State()
    entering_order_id_for_status_change = State()
    editing_order = State()
    # Stats
    choosing_stats_start_date = State()
    choosing_stats_end_date = State()
    # Promocodes
    entering_promocode_code = State()
    entering_promocode_discount = State()
    choosing_promocode_start_date = State()
    choosing_promocode_end_date = State()
    entering_promocode_limit = State()
    # Price management
    entering_new_price = State()
    # Day management
    choosing_date_to_toggle_block = State()
    # Client management
    entering_new_client_name = State()
    # Candidate management
    viewing_candidate = State()
    # Admin management
    entering_add_admin_id = State()