CREATE_TABLES_SQL = """
-- Создаем ENUM типы для статусов, чтобы обеспечить целостность данных
-- Для добавления нового статуса в существующую базу может потребоваться выполнить вручную:
-- ALTER TYPE booking_status ADD VALUE 'pending_confirmation' BEFORE 'confirmed';
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'booking_status') THEN
        -- Создаем тип сразу со всеми нужными значениями
        CREATE TYPE booking_status AS ENUM ('pending_confirmation', 'confirmed', 'completed', 'cancelled_by_user', 'cancelled_by_admin');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'order_status') THEN
        CREATE TYPE order_status AS ENUM ('processing', 'assembled', 'shipped', 'completed', 'cancelled');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'promo_type') THEN
        CREATE TYPE promo_type AS ENUM ('shop', 'detailing');
    END IF;
END$$;

-- Таблица пользователей
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    full_name TEXT NOT NULL,
    username TEXT,
    first_seen TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    is_blocked BOOLEAN DEFAULT FALSE,
    is_admin BOOLEAN DEFAULT FALSE
);

-- Добавляем колонку для заметок, если она не существует (для обратной совместимости)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='internal_note') THEN
        ALTER TABLE users ADD COLUMN internal_note TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='phone_number') THEN
        ALTER TABLE users ADD COLUMN phone_number TEXT;
    END IF;
END$$;

-- Таблица для промокодов
CREATE TABLE IF NOT EXISTS promocodes (
    code TEXT PRIMARY KEY,
    promo_type promo_type NOT NULL,
    discount_percent SMALLINT NOT NULL CHECK (discount_percent > 0 AND discount_percent <= 100),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    usage_limit INT,
    times_used INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Таблица для записей на услуги
CREATE TABLE IF NOT EXISTS bookings (
    booking_id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    service_name TEXT NOT NULL,
    booking_date DATE NOT NULL,
    booking_time TIME NOT NULL,
    price_rub INT NOT NULL, -- Цена в рублях
    discount_rub INT DEFAULT 0,
    promocode TEXT REFERENCES promocodes(code),
    status booking_status DEFAULT 'pending_confirmation',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    details_json JSONB -- Для хранения всех деталей выбора пользователя
);
CREATE INDEX IF NOT EXISTS idx_bookings_user_id ON bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_date_time ON bookings(booking_date, booking_time);

-- Таблица для медиафайлов, привязанных к записям
CREATE TABLE IF NOT EXISTS booking_media (
    media_id SERIAL PRIMARY KEY,
    booking_id INT NOT NULL REFERENCES bookings(booking_id) ON DELETE CASCADE,
    file_id TEXT NOT NULL,
    file_type TEXT NOT NULL -- 'photo' или 'video'
);
CREATE INDEX IF NOT EXISTS idx_booking_media_booking_id ON booking_media(booking_id);

-- Таблица для заказов из магазина
CREATE TABLE IF NOT EXISTS orders (
    order_id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    items_price_rub INT NOT NULL,
    delivery_cost_rub INT DEFAULT 0,
    discount_rub INT DEFAULT 0,
    total_price_rub INT NOT NULL,
    promocode TEXT REFERENCES promocodes(code),
    shipping_method TEXT,
    shipping_address TEXT,
    status order_status DEFAULT 'processing',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);

-- Таблица для товаров в заказе (связующая)
CREATE TABLE IF NOT EXISTS order_items (
    item_id SERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id TEXT NOT NULL, -- Внешний ключ на будущую таблицу товаров
    quantity INT NOT NULL CHECK (quantity > 0),
    price_per_item_rub INT NOT NULL -- Цена на момент покупки
);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);

-- Таблица для заблокированных вручную дат
CREATE TABLE IF NOT EXISTS blocked_dates (
    blocked_date DATE PRIMARY KEY
);

-- Таблица для кандидатов на работу
CREATE TABLE IF NOT EXISTS candidates (
    candidate_id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    full_name TEXT NOT NULL,
    username TEXT,
    message_text TEXT,
    file_id TEXT,
    file_name TEXT,
    received_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Таблица категорий товаров
CREATE TABLE IF NOT EXISTS product_categories (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

-- Таблица товаров
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    price INT NOT NULL,
    description TEXT,
    image_url TEXT,
    detail_images JSONB,
    category_id TEXT NOT NULL REFERENCES product_categories(id) ON DELETE RESTRICT,
    subcategory TEXT
);
CREATE INDEX IF NOT EXISTS idx_products_category_id ON products(category_id);
"""