import asyncio
import os
import pytest
from httpx import AsyncClient
import psycopg

# Set environment variable to redirect to test database BEFORE importing modules
os.environ["POSTGRES_DB"] = "einkaufsliste-test"

import database
from main import app

@pytest.fixture(scope="session", autouse=True)
def _fresh_test_db():
    """
    Drop and recreate the test database once per test session, before any
    schema setup runs. Without this, a stale local/CI database that already
    has tables from a previous run can mask bugs in init_db()'s DDL
    ordering (e.g. a migration that references a table created later).
    """
    from config import settings

    async def _reset():
        admin_conn_str = f"host={settings.postgres_host} port={settings.postgres_port} user={settings.postgres_user} password={settings.postgres_password} dbname=postgres sslmode=disable"
        conn = await psycopg.AsyncConnection.connect(admin_conn_str, autocommit=True)
        async with conn:
            async with conn.cursor() as cur:
                await cur.execute('DROP DATABASE IF EXISTS "einkaufsliste-test" WITH (FORCE);')
                await cur.execute('CREATE DATABASE "einkaufsliste-test";')

    asyncio.run(_reset())

@pytest.fixture(autouse=True)
async def setup_test_db():
    # Open connections pool and trigger schema setup/migrations on test DB
    await database.init_db()
    
    yield
    
    # 3. Clean up: close the pool
    pool = database.get_pool()
    await pool.close()
    # Reset global pool to None so it can be re-initialized in the next test
    database.pool = None

@pytest.fixture(autouse=True)
async def clean_db(setup_test_db):
    """
    Cleans and re-seeds database defaults before each individual test case.
    Ensures complete test isolation.
    """
    import time
    p = database.get_pool()
    async with p.connection() as conn:
        async with conn.cursor() as cur:
            # Cascade truncate all tables to start fresh and reset auto-increment sequences
            await cur.execute("TRUNCATE items, stores, categories, pets, pet_logs, recipes, recipe_ingredients RESTART IDENTITY CASCADE;")
            
            # Re-seed default lookup records (will get ID 1 naturally)
            await cur.execute("INSERT INTO categories (name, color) VALUES ('keine', '#ffffff');")
            await cur.execute("INSERT INTO stores (name) VALUES ('keiner');")
            
            # Reset pet state
            now_ts = int(time.time())
            await cur.execute("""
                INSERT INTO pets (name, fed_at, amount_fed, is_inside, inside_at)
                VALUES ('Companion', %s, '', FALSE, %s) RETURNING id;
            """, (now_ts, now_ts))
            pet_id = (await cur.fetchone())[0]
            await cur.execute("""
                INSERT INTO pet_logs (pet_id, activity_type, detail)
                VALUES (%s, 'created', 'Default companion created during test setup');
            """, (pet_id,))
            
            await conn.commit()

from httpx import AsyncClient, ASGITransport

@pytest.fixture
async def client():
    """
    Async client for hitting FastAPI endpoints.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
