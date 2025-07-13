import logging
import os
import json
from .pool import get_pool

logger = logging.getLogger(__name__)


async def force_sync_products_from_json():
    """
    Принудительно очищает таблицу продуктов и загружает в нее свежие данные из products.json.
    ЭТО ОПАСНАЯ ОПЕРАЦИЯ, ИСПОЛЬЗОВАТЬ ТОЛЬКО ДЛЯ РАЗОВОЙ СИНХРОНИЗАЦИИ.
    """
    logger.warning("!!! RUNNING DANGEROUS OPERATION: force_sync_products_from_json !!!")

    products_path = os.path.join('data', 'products.json')

    try:
        with open(products_path, 'r', encoding='utf-8-sig') as f:
            products_from_file = json.load(f)
        logger.info(f"Successfully loaded {len(products_from_file)} products from {products_path}")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.critical(f"Could not load or parse {products_path}. Aborting sync. Error: {e}")
        return

    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            # Шаг 1: Убедимся, что все категории из файла существуют в БД
            unique_categories = {p.get('category') for p in products_from_file if p.get('category')}
            logger.info(f"Found unique categories in file: {unique_categories}")
            if unique_categories:
                for category_name in unique_categories:
                    # Используем category_name и как ID, и как имя для простоты
                    await connection.execute(
                        "INSERT INTO product_categories (id, name) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING",
                        category_name, category_name
                    )
                logger.info("Ensured all product categories exist in the database.")

            # Шаг 2: Полностью очищаем таблицу продуктов
            await connection.execute("DELETE FROM products;")
            logger.info("Table 'products' has been cleared.")

            # Шаг 3: Вставляем новые данные о продуктах
            for product in products_from_file:
                await connection.execute(
                    """
                    INSERT INTO products (id, name, price, category_id, subcategory, image_url, description, detail_images)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    product.get('id'), product.get('name'), product.get('price'), product.get('category'),
                    product.get('subcategory'), product.get('image_url'), product.get('description'),
                    json.dumps(product.get('detail_images', []))
                )
    logger.warning("!!! FINISHED DANGEROUS OPERATION: force_sync_products_from_json !!!")
    logger.info(f"Successfully inserted {len(products_from_file)} products into the database.")