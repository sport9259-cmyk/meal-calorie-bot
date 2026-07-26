import sqlite3
from datetime import datetime, date
from contextlib import contextmanager

from config import DB_PATH


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                name TEXT,
                gender TEXT,           -- 'male' / 'female'
                weight_kg REAL,
                height_cm REAL,
                age INTEGER,
                activity_level TEXT,   -- 'low' / 'medium' / 'high'
                calorie_target REAL,
                onboarded INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                meal_date TEXT,        -- YYYY-MM-DD (بتوقيت بغداد)
                description TEXT,
                calories REAL,
                created_at TEXT
            )
        """)


def upsert_user_profile(chat_id, gender, weight_kg, height_cm, age, activity_level, calorie_target):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO users (chat_id, gender, weight_kg, height_cm, age, activity_level, calorie_target, onboarded, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                gender=excluded.gender,
                weight_kg=excluded.weight_kg,
                height_cm=excluded.height_cm,
                age=excluded.age,
                activity_level=excluded.activity_level,
                calorie_target=excluded.calorie_target,
                onboarded=1
        """, (chat_id, gender, weight_kg, height_cm, age, activity_level, calorie_target, datetime.now().isoformat()))


def get_user(chat_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
        return dict(row) if row else None


def get_all_onboarded_users():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM users WHERE onboarded = 1").fetchall()
        return [dict(r) for r in rows]


def add_meal(chat_id, meal_date, description, calories):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO meals (chat_id, meal_date, description, calories, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (chat_id, meal_date, description, calories, datetime.now().isoformat()))


def get_meals_for_day(chat_id, meal_date):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM meals WHERE chat_id = ? AND meal_date = ? ORDER BY created_at
        """, (chat_id, meal_date)).fetchall()
        return [dict(r) for r in rows]
