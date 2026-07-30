import logging
import time
from typing import List, Optional, Dict, Any
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from config import settings

logger = logging.getLogger(__name__)

# Global connection pool
pool: Optional[AsyncConnectionPool] = None

def get_pool() -> AsyncConnectionPool:
    global pool
    if pool is None:
        logger.info(f"Initializing connection pool with: {settings.database_dsn}")
        pool = AsyncConnectionPool(
            conninfo=settings.database_dsn,
            open=False,
            min_size=1,
            max_size=10
        )
    return pool

async def init_db():
    p = get_pool()
    await p.open()

    async with p.connection() as conn:
        async with conn.cursor() as cur:
            # 1. Create Core Tables
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    color VARCHAR NOT NULL
                );
            """)

            await cur.execute("""
                CREATE TABLE IF NOT EXISTS stores (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR NOT NULL
                );
            """)

            await cur.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    note VARCHAR NOT NULL DEFAULT '',
                    amount INTEGER NOT NULL,
                    status VARCHAR NOT NULL DEFAULT 'new',
                    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                    store_id INTEGER REFERENCES stores(id) ON DELETE SET NULL
                );
            """)

            # 2. Add New Schema Columns & Constraints (Safe migrations)
            await cur.execute("ALTER TABLE categories ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();")
            await cur.execute("ALTER TABLE categories ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();")

            await cur.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();")
            await cur.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();")

            await cur.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();")
            await cur.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();")
            await cur.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS image_path VARCHAR;")
            await cur.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS favorite BOOLEAN NOT NULL DEFAULT FALSE;")

            # Check constraint for positive amount
            await cur.execute("ALTER TABLE items DROP CONSTRAINT IF EXISTS check_amount_positive;")
            await cur.execute("ALTER TABLE items ADD CONSTRAINT check_amount_positive CHECK (amount > 0);")

            # Check constraint for valid hex color format
            await cur.execute("ALTER TABLE categories DROP CONSTRAINT IF EXISTS check_valid_hex_color;")
            await cur.execute("ALTER TABLE categories ADD CONSTRAINT check_valid_hex_color CHECK (color ~ '^#(?:[0-9a-fA-F]{3}){1,2}$');")

            # 3. Create Indexes for Optimization & Case-Insensitivity
            await cur.execute("ALTER TABLE categories DROP CONSTRAINT IF EXISTS categories_name_key;")
            await cur.execute("ALTER TABLE stores DROP CONSTRAINT IF EXISTS stores_name_key;")
            await cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_categories_name_lower ON categories (LOWER(name));")
            await cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_stores_name_lower ON stores (LOWER(name));")

            await cur.execute("CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);")
            await cur.execute("CREATE INDEX IF NOT EXISTS idx_items_store_id ON items(store_id);")
            await cur.execute("CREATE INDEX IF NOT EXISTS idx_items_category_id ON items(category_id);")

            # 4. Create Triggers for Auto-updating updated_at columns
            await cur.execute("""
                CREATE OR REPLACE FUNCTION update_modified_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = NOW();
                    RETURN NEW;
                END;
                $$ language 'plpgsql';
            """)

            await cur.execute("""
                DROP TRIGGER IF EXISTS update_items_modtime ON items;
                CREATE TRIGGER update_items_modtime BEFORE UPDATE ON items FOR EACH ROW EXECUTE PROCEDURE update_modified_column();
            """)

            await cur.execute("""
                DROP TRIGGER IF EXISTS update_stores_modtime ON stores;
                CREATE TRIGGER update_stores_modtime BEFORE UPDATE ON stores FOR EACH ROW EXECUTE PROCEDURE update_modified_column();
            """)

            await cur.execute("""
                DROP TRIGGER IF EXISTS update_categories_modtime ON categories;
                CREATE TRIGGER update_categories_modtime BEFORE UPDATE ON categories FOR EACH ROW EXECUTE PROCEDURE update_modified_column();
            """)

            # 5. Drop old single-row pet_state and create dynamic pets & logs tables
            await cur.execute("DROP TABLE IF EXISTS pet_state;")

            await cur.execute("""
                CREATE TABLE IF NOT EXISTS pets (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR UNIQUE NOT NULL,
                    fed_at BIGINT NOT NULL,
                    amount_fed VARCHAR NOT NULL DEFAULT '',
                    is_inside BOOLEAN NOT NULL DEFAULT FALSE,
                    inside_at BIGINT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)

            await cur.execute("""
                CREATE TABLE IF NOT EXISTS pet_logs (
                    id SERIAL PRIMARY KEY,
                    pet_id INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
                    activity_type VARCHAR NOT NULL,
                    detail VARCHAR NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)

            # 6. Create trigger for pets updated_at
            await cur.execute("""
                DROP TRIGGER IF EXISTS update_pets_modtime ON pets;
                CREATE TRIGGER update_pets_modtime BEFORE UPDATE ON pets FOR EACH ROW EXECUTE PROCEDURE update_modified_column();
            """)

            # Get current Unix timestamp and seed default pet if empty
            now_ts = int(time.time())
            await cur.execute("SELECT COUNT(*) FROM pets;")
            count_row = await cur.fetchone()
            if count_row[0] == 0:
                await cur.execute("""
                    INSERT INTO pets (name, fed_at, amount_fed, is_inside, inside_at)
                    VALUES ('Companion', %s, '', FALSE, %s) RETURNING id;
                """, (now_ts, now_ts))
                seeded_id = (await cur.fetchone())[0]
                await cur.execute("""
                    INSERT INTO pet_logs (pet_id, activity_type, detail)
                    VALUES (%s, 'created', 'Default companion created during system initialization');
                """, (seeded_id,))

            # Create Recipes and Recipe Ingredients tables
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS recipes (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    description VARCHAR NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)

            await cur.execute("""
                CREATE TABLE IF NOT EXISTS recipe_ingredients (
                    id SERIAL PRIMARY KEY,
                    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
                    name VARCHAR NOT NULL,
                    amount INTEGER NOT NULL DEFAULT 1,
                    note VARCHAR NOT NULL DEFAULT '',
                    store_id INTEGER REFERENCES stores(id) ON DELETE SET NULL,
                    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL
                );
            """)

            await cur.execute("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS image_path VARCHAR;")

            await cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_recipes_name_lower ON recipes (LOWER(name));")

            await cur.execute("""
                DROP TRIGGER IF EXISTS update_recipes_modtime ON recipes;
                CREATE TRIGGER update_recipes_modtime BEFORE UPDATE ON recipes FOR EACH ROW EXECUTE PROCEDURE update_modified_column();
            """)

            # Create Meal Plans table
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS meal_plans (
                    id SERIAL PRIMARY KEY,
                    date VARCHAR NOT NULL,
                    meal_type VARCHAR NOT NULL,
                    recipe_id INTEGER REFERENCES recipes(id) ON DELETE CASCADE,
                    note VARCHAR,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)

            await cur.execute("""
                DROP TRIGGER IF EXISTS update_meal_plans_modtime ON meal_plans;
                CREATE TRIGGER update_meal_plans_modtime BEFORE UPDATE ON meal_plans FOR EACH ROW EXECUTE PROCEDURE update_modified_column();
            """)

            # 6. Initialize Default Category & Store if missing
            await cur.execute("SELECT id FROM categories WHERE name = %s;", ("keine",))
            row = await cur.fetchone()
            if not row:
                await cur.execute("INSERT INTO categories (name, color) VALUES (%s, %s);", ("keine", "#ffffff"))

            await cur.execute("SELECT id FROM stores WHERE name = %s;", ("keiner",))
            row = await cur.fetchone()
            if not row:
                await cur.execute("INSERT INTO stores (name) VALUES (%s);", ("keiner",))
            
            await conn.commit()
    logger.info("Database schema updated and triggers configured.")

#
# CATEGORY QUERIES
#

async def get_all_categories() -> List[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("""
                SELECT c.id, c.name, c.color, c.created_at, c.updated_at, COUNT(i.id)::int AS item_count
                FROM categories c
                LEFT JOIN items i ON i.category_id = c.id
                GROUP BY c.id, c.name, c.color, c.created_at, c.updated_at
                ORDER BY c.id;
            """)
            return await cur.fetchall()

async def get_category_by_id(cat_id: int) -> Optional[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("""
                SELECT c.id, c.name, c.color, c.created_at, c.updated_at, COUNT(i.id)::int AS item_count
                FROM categories c
                LEFT JOIN items i ON i.category_id = c.id
                WHERE c.id = %s
                GROUP BY c.id, c.name, c.color, c.created_at, c.updated_at;
            """, (cat_id,))
            return await cur.fetchone()

async def create_category(name: str, color: str) -> None:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO categories (name, color) VALUES (%s, %s);", (name, color))
            await conn.commit()

async def update_category(cat_id: int, name: str, color: str) -> None:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE categories SET name = %s, color = %s WHERE id = %s;", (name, color, cat_id))
            await conn.commit()

async def delete_category(cat_id: int) -> None:
    if cat_id == 1:
        raise ValueError("cannot delete the default category")
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor() as cur:
            # Re-associate any items pointing to the deleted category back to category 1 ('keine')
            await cur.execute("UPDATE items SET category_id = 1 WHERE category_id = %s;", (cat_id,))
            await cur.execute("DELETE FROM categories WHERE id = %s;", (cat_id,))
            await conn.commit()

#
# STORE QUERIES
#

async def get_all_stores() -> List[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("""
                SELECT s.id, s.name, s.created_at, s.updated_at, COUNT(i.id)::int AS item_count
                FROM stores s
                LEFT JOIN items i ON i.store_id = s.id
                GROUP BY s.id, s.name, s.created_at, s.updated_at
                ORDER BY s.id;
            """)
            return await cur.fetchall()

async def get_store_by_id(store_id: int) -> Optional[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("""
                SELECT s.id, s.name, s.created_at, s.updated_at, COUNT(i.id)::int AS item_count
                FROM stores s
                LEFT JOIN items i ON i.store_id = s.id
                WHERE s.id = %s
                GROUP BY s.id, s.name, s.created_at, s.updated_at;
            """, (store_id,))
            return await cur.fetchone()

async def create_store(name: str) -> None:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO stores (name) VALUES (%s);", (name,))
            await conn.commit()

async def update_store(store_id: int, name: str) -> None:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE stores SET name = %s WHERE id = %s;", (name, store_id))
            await conn.commit()

async def delete_store(store_id: int) -> None:
    if store_id == 1:
        raise ValueError("cannot delete the default store")
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor() as cur:
            # Re-associate any items pointing to the deleted store back to store 1 ('keiner')
            await cur.execute("UPDATE items SET store_id = 1 WHERE store_id = %s;", (store_id,))
            await cur.execute("DELETE FROM stores WHERE id = %s;", (store_id,))
            await conn.commit()

#
# ITEM QUERIES
#
ITEM_ORDER_BY = "ORDER BY store_id ASC, category_id ASC, name ASC"

async def get_all_items() -> List[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(f"SELECT id, name, note, amount, status, store_id, category_id, image_path, favorite, created_at, updated_at FROM items {ITEM_ORDER_BY};")
            return await cur.fetchall()

async def get_item_by_id(item_id: int) -> Optional[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT id, name, note, amount, status, store_id, category_id, image_path, favorite, created_at, updated_at FROM items WHERE id = %s;", (item_id,))
            return await cur.fetchone()

async def get_items_filtered(
    status: Optional[str] = None,
    store_id: Optional[int] = None,
    category_id: Optional[int] = None,
    store_name: Optional[str] = None,
    category_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            query = """
                SELECT i.id, i.name, i.note, i.amount, i.status, i.store_id, i.category_id, i.image_path, i.created_at, i.updated_at 
                FROM items i
                LEFT JOIN stores s ON i.store_id = s.id
                LEFT JOIN categories c ON i.category_id = c.id
                WHERE 1=1
            """
            params = []
            
            if status:
                query += " AND i.status = %s"
                params.append(status)
            if store_id is not None:
                query += " AND i.store_id = %s"
                params.append(store_id)
            if category_id is not None:
                query += " AND i.category_id = %s"
                params.append(category_id)
            if store_name:
                query += " AND s.name = %s"
                params.append(store_name)
            if category_name:
                query += " AND c.name = %s"
                params.append(category_name)
                
            query += f" {ITEM_ORDER_BY}"
            await cur.execute(query, params)
            return await cur.fetchall()

async def create_item(name: str, note: str, amount: int, store_id: Optional[int], category_id: Optional[int], favorite: bool = False) -> None:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            # Predict store and category based on past entries if not explicitly provided
            pred_store_id = store_id
            pred_category_id = category_id
            
            if not pred_store_id or pred_store_id == 1 or not pred_category_id or pred_category_id == 1:
                # Find most recent item with same name that has non-default store/category
                await cur.execute("""
                    SELECT store_id, category_id 
                    FROM items 
                    WHERE LOWER(name) = LOWER(%s) AND (
                        (store_id IS NOT NULL AND store_id != 1) OR 
                        (category_id IS NOT NULL AND category_id != 1)
                    )
                    ORDER BY id DESC 
                    LIMIT 1;
                """, (name,))
                past_item = await cur.fetchone()
                if past_item:
                    if (not pred_store_id or pred_store_id == 1) and past_item["store_id"]:
                        pred_store_id = past_item["store_id"]
                    if (not pred_category_id or pred_category_id == 1) and past_item["category_id"]:
                        pred_category_id = past_item["category_id"]
            
            final_store_id = pred_store_id if pred_store_id is not None else 1
            final_category_id = pred_category_id if pred_category_id is not None else 1
            
            await cur.execute(
                """
                INSERT INTO items (name, note, amount, status, store_id, category_id, favorite)
                VALUES (%s, %s, %s, 'new', %s, %s, %s);
                """,
                (name, note, amount, final_store_id, final_category_id, favorite)
            )
            await conn.commit()

async def update_item(item_id: int, name: str, note: str, amount: int, store_id: Optional[int], category_id: Optional[int], favorite: bool = False) -> None:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE items
                SET name = %s, note = %s, amount = %s, store_id = %s, category_id = %s, favorite = %s
                WHERE id = %s;
                """,
                (name, note, amount, store_id, category_id, favorite, item_id)
            )
            await conn.commit()

async def delete_item(item_id: int) -> None:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM items WHERE id = %s;", (item_id,))
            await conn.commit()

async def switch_item_status(item_id: int) -> None:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT status FROM items WHERE id = %s;", (item_id,))
            item = await cur.fetchone()
            if not item:
                raise ValueError(f"item with id {item_id} not found")
            
            new_status = "bought" if item["status"] == "new" else "new"
            await cur.execute(
                "UPDATE items SET status = %s WHERE id = %s;",
                (new_status, item_id)
            )
            await conn.commit()

async def suggest_item_names(query: str) -> List[str]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor() as cur:
            db_query = f"{query.strip()}%"
            await cur.execute(
                """
                SELECT name, COUNT(*) as frequency
                FROM items
                WHERE LOWER(name) LIKE LOWER(%s)
                GROUP BY name
                ORDER BY frequency DESC, name ASC
                LIMIT 10;
                """,
                (db_query,)
            )
            rows = await cur.fetchall()
            return [row[0] for row in rows]

async def archive_bought_items() -> int:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM items WHERE status = 'bought';")
            deleted_count = cur.rowcount
            await conn.commit()
            return deleted_count

async def get_frequent_items() -> List[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("""
                SELECT name, store_id, category_id, COUNT(*)::int as purchase_count
                FROM items
                WHERE LOWER(name) NOT IN (
                    SELECT DISTINCT LOWER(name) FROM items WHERE status = 'new'
                )
                GROUP BY name, store_id, category_id
                ORDER BY purchase_count DESC, name ASC
                LIMIT 10;
            """)
            return await cur.fetchall()

#
# PET QUERIES
#

async def get_first_pet() -> Optional[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT id, name, fed_at, amount_fed, is_inside, inside_at, created_at, updated_at FROM pets ORDER BY id LIMIT 1;")
            return await cur.fetchone()

async def get_all_pets() -> List[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT id, name, fed_at, amount_fed, is_inside, inside_at, created_at, updated_at FROM pets ORDER BY id;")
            return await cur.fetchall()

async def get_pet_by_id(pet_id: int) -> Optional[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT id, name, fed_at, amount_fed, is_inside, inside_at, created_at, updated_at FROM pets WHERE id = %s;", (pet_id,))
            return await cur.fetchone()

async def create_pet(name: str) -> Dict[str, Any]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            now = int(time.time())
            await cur.execute(
                """
                INSERT INTO pets (name, fed_at, amount_fed, is_inside, inside_at)
                VALUES (%s, %s, '', FALSE, %s)
                RETURNING id, name, fed_at, amount_fed, is_inside, inside_at, created_at, updated_at;
                """,
                (name, now, now)
            )
            new_pet = await cur.fetchone()
            
            # Log creation
            await cur.execute(
                "INSERT INTO pet_logs (pet_id, activity_type, detail) VALUES (%s, 'created', %s);",
                (new_pet["id"], f"Pet created with name: {name}")
            )
            await conn.commit()
            return new_pet

async def update_pet_name(pet_id: int, name: str) -> Optional[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "UPDATE pets SET name = %s WHERE id = %s RETURNING id, name, fed_at, amount_fed, is_inside, inside_at, created_at, updated_at;",
                (name, pet_id)
            )
            updated = await cur.fetchone()
            if updated:
                await cur.execute(
                    "INSERT INTO pet_logs (pet_id, activity_type, detail) VALUES (%s, 'renamed', %s);",
                    (pet_id, f"Renamed to: {name}")
                )
                await conn.commit()
            return updated

async def delete_pet(pet_id: int) -> None:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM pets WHERE id = %s;", (pet_id,))
            await conn.commit()

async def update_pet_location(pet_id: int) -> Dict[str, Any]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT is_inside FROM pets WHERE id = %s;", (pet_id,))
            row = await cur.fetchone()
            if not row:
                raise ValueError(f"pet with id {pet_id} not found")
            
            new_inside = not row["is_inside"]
            now = int(time.time())
            await cur.execute(
                "UPDATE pets SET is_inside = %s, inside_at = %s WHERE id = %s RETURNING id, name, fed_at, amount_fed, is_inside, inside_at, created_at, updated_at;",
                (new_inside, now, pet_id)
            )
            updated = await cur.fetchone()
            
            # Log location change
            detail_str = "Moved inside" if new_inside else "Moved outside"
            await cur.execute(
                "INSERT INTO pet_logs (pet_id, activity_type, detail) VALUES (%s, 'location_change', %s);",
                (pet_id, detail_str)
            )
            await conn.commit()
            return updated

async def feed_pet(pet_id: int, amount: str) -> Dict[str, Any]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            # Check if pet exists
            await cur.execute("SELECT id FROM pets WHERE id = %s;", (pet_id,))
            row = await cur.fetchone()
            if not row:
                raise ValueError(f"pet with id {pet_id} not found")
                
            now = int(time.time())
            await cur.execute(
                "UPDATE pets SET fed_at = %s, amount_fed = %s WHERE id = %s RETURNING id, name, fed_at, amount_fed, is_inside, inside_at, created_at, updated_at;",
                (now, amount, pet_id)
            )
            updated = await cur.fetchone()
            
            # Log feeding activity
            await cur.execute(
                "INSERT INTO pet_logs (pet_id, activity_type, detail) VALUES (%s, 'fed', %s);",
                (pet_id, f"Fed portion: {amount}")
            )
            await conn.commit()
            return updated

async def get_pet_logs(pet_id: int) -> List[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, pet_id, activity_type, detail, created_at FROM pet_logs WHERE pet_id = %s ORDER BY created_at DESC;",
                (pet_id,)
            )
            return await cur.fetchall()


#
# RECIPE QUERIES
#

async def get_all_recipes() -> List[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT id, name, description, image_path, created_at, updated_at FROM recipes ORDER BY id;")
            return await cur.fetchall()

async def get_recipe_by_id(recipe_id: int) -> Optional[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT id, name, description, image_path, created_at, updated_at FROM recipes WHERE id = %s;", (recipe_id,))
            return await cur.fetchone()

async def get_recipe_ingredients(recipe_id: int) -> List[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT id, recipe_id, name, amount, note, store_id, category_id 
                FROM recipe_ingredients 
                WHERE recipe_id = %s 
                ORDER BY id;
                """,
                (recipe_id,)
            )
            return await cur.fetchall()

async def create_recipe(name: str, description: str, ingredients: List[Dict[str, Any]]) -> Dict[str, Any]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            # Insert recipe
            await cur.execute(
                "INSERT INTO recipes (name, description) VALUES (%s, %s) RETURNING id, name, description, image_path, created_at, updated_at;",
                (name, description)
            )
            recipe_row = await cur.fetchone()
            recipe_id = recipe_row["id"]
            
            # Insert ingredients
            inserted_ingredients = []
            for ing in ingredients:
                await cur.execute(
                    """
                    INSERT INTO recipe_ingredients (recipe_id, name, amount, note, store_id, category_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, recipe_id, name, amount, note, store_id, category_id;
                    """,
                    (
                        recipe_id,
                        ing["name"],
                        ing.get("amount", 1),
                        ing.get("note", ""),
                        ing.get("store_id"),
                        ing.get("category_id")
                    )
                )
                inserted_ingredients.append(await cur.fetchone())
                
            await conn.commit()
            
            recipe_row["ingredients"] = inserted_ingredients
            return recipe_row

async def update_recipe(recipe_id: int, name: str, description: str, ingredients: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            # Check if exists
            await cur.execute("SELECT id FROM recipes WHERE id = %s;", (recipe_id,))
            if not await cur.fetchone():
                return None
                
            # Update recipe
            await cur.execute(
                "UPDATE recipes SET name = %s, description = %s WHERE id = %s RETURNING id, name, description, image_path, created_at, updated_at;",
                (name, description, recipe_id)
            )
            recipe_row = await cur.fetchone()
            
            # Delete old ingredients
            await cur.execute("DELETE FROM recipe_ingredients WHERE recipe_id = %s;", (recipe_id,))
            
            # Insert new ingredients
            inserted_ingredients = []
            for ing in ingredients:
                await cur.execute(
                    """
                    INSERT INTO recipe_ingredients (recipe_id, name, amount, note, store_id, category_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, recipe_id, name, amount, note, store_id, category_id;
                    """,
                    (
                        recipe_id,
                        ing["name"],
                        ing.get("amount", 1),
                        ing.get("note", ""),
                        ing.get("store_id"),
                        ing.get("category_id")
                    )
                )
                inserted_ingredients.append(await cur.fetchone())
                
            await conn.commit()
            
            recipe_row["ingredients"] = inserted_ingredients
            return recipe_row

async def delete_recipe(recipe_id: int) -> None:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM recipes WHERE id = %s;", (recipe_id,))
            await conn.commit()

async def add_recipe_to_shopping_list(recipe_id: int) -> int:
    # 1. Fetch all ingredients
    ingredients = await get_recipe_ingredients(recipe_id)
    if not ingredients:
        return 0
        
    # 2. Add each ingredient as an active item
    # We call our existing create_item which handles predicting store/category if they are None or 1!
    for ing in ingredients:
        await create_item(
            name=ing["name"],
            note=ing["note"],
            amount=ing["amount"],
            store_id=ing["store_id"],
            category_id=ing["category_id"]
        )
    return len(ingredients)

async def update_item_image(item_id: int, image_path: Optional[str]) -> Optional[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "UPDATE items SET image_path = %s WHERE id = %s RETURNING id, name, note, amount, status, store_id, category_id, image_path, favorite, created_at, updated_at;",
                (image_path, item_id)
            )
            updated = await cur.fetchone()
            await conn.commit()
            return updated

async def update_recipe_image(recipe_id: int, image_path: Optional[str]) -> Optional[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            # Update image path
            await cur.execute(
                "UPDATE recipes SET image_path = %s WHERE id = %s RETURNING id, name, description, image_path, created_at, updated_at;",
                (image_path, recipe_id)
            )
            recipe_row = await cur.fetchone()
            if recipe_row:
                recipe_row["ingredients"] = await get_recipe_ingredients(recipe_id)
            await conn.commit()
            return recipe_row


#
# MEAL PLAN QUERIES
#

async def get_all_meal_plans() -> List[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("""
                SELECT mp.*, 
                       r.name as recipe_name, r.description as recipe_description, r.image_path as recipe_image_path
                FROM meal_plans mp
                LEFT JOIN recipes r ON mp.recipe_id = r.id
                ORDER BY mp.date ASC, 
                         CASE mp.meal_type 
                            WHEN 'Frühstück' THEN 1 
                            WHEN 'Mittagessen' THEN 2 
                            WHEN 'Abendessen' THEN 3 
                            ELSE 4 
                         END;
            """)
            return await cur.fetchall()

async def get_meal_plan_by_id(plan_id: int) -> Optional[Dict[str, Any]]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("""
                SELECT mp.*, 
                       r.name as recipe_name, r.description as recipe_description, r.image_path as recipe_image_path
                FROM meal_plans mp
                LEFT JOIN recipes r ON mp.recipe_id = r.id
                WHERE mp.id = %s;
            """, (plan_id,))
            return await cur.fetchone()

async def create_meal_plan(date: str, meal_type: str, recipe_id: Optional[int], note: Optional[str]) -> Dict[str, Any]:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("""
                INSERT INTO meal_plans (date, meal_type, recipe_id, note)
                VALUES (%s, %s, %s, %s)
                RETURNING id, date, meal_type, recipe_id, note, created_at, updated_at;
            """, (date, meal_type, recipe_id, note))
            row = await cur.fetchone()
            await conn.commit()
            return row

async def delete_meal_plan(plan_id: int) -> None:
    p = get_pool()
    async with p.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM meal_plans WHERE id = %s;", (plan_id,))
            await conn.commit()
