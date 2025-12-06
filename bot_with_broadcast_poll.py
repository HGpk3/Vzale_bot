import asyncio
import os
import logging
import aiosqlite
import json
import uuid
import random
import string
import sqlite3
import html
import aiohttp
import bcrypt

import aiosqlite, re
from dotenv import load_dotenv
from aiogram.exceptions import TelegramBadRequest



from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, PollAnswer, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.state import State, StatesGroup

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties


def gen_invite_code(n: int = 6) -> str:
    # 6-символьный код из заглавных букв и цифр, можно поменять на только цифры, если хочешь
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(n))

async def get_team_by_code(code: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT team_name FROM team_security WHERE invite_code = ?", (code.strip().upper(),))
        row = await cur.fetchone()
        return row[0] if row else None



load_dotenv()
WEB_AUTH_BASE = "https://vzale-site.vercel.app/me"
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "tournament.db"
GLOBAL_TOURNAMENT_ID = 0  # "за всё время" / глобальная выдача
ADMINS = [409436763, 469460286]
# === RATING COEFFICIENTS (simple) ===
K_WIN = 20        # победа команды
K_LOSS = -5       # поражение команды
K_POINT = 2.0     # очки
K_AST = 3.0       # ассисты
K_BLK = 4.0       # блоки

# бонус победителю за разницу счёта (каждые 5 очков разницы)
MARGIN_BUCKET = 5
K_MARGIN_STEP = 1

# бонус лучшему бомбардиру матча (0 — отключить)
K_TOP_SCORER = 5


import asyncio

db_lock = asyncio.Lock()

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

class Form(StatesGroup):
    # твои старые состояния
    waiting_for_name = State()
    waiting_for_team_status = State()
    waiting_for_team_name = State()
    waiting_for_team_selection = State()
    waiting_for_free_info = State()
    waiting_for_invite_code = State()
    # ↓↓↓ отдельное состояние под регистрацию из меню турнира
    waiting_for_team_name_in_tournament = State()

    # новые состояния для веб-логина
    waiting_for_web_username = State()
    waiting_for_web_password = State()

class AdminForm(StatesGroup):
    waiting_broadcast_text = State()
    waiting_poll_question = State()
    waiting_poll_options = State()
    waiting_tinfo_section_key = State()
    waiting_tinfo_section_text = State()
    waiting_tournament_name = State()   # ← НОВОЕ состояние для ввода названия турнира

class AdminTT(StatesGroup):
    waiting_team_name = State()

class AdminMatches(StatesGroup):
    add_pick_home = State()
    add_pick_away = State()
    add_pick_stage = State()
    score_wait_value = State()


class SuggestionForm(StatesGroup):
    waiting_text = State()

class AdminReplyForm(StatesGroup):
    waiting_text = State()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def set_web_user(telegram_id: int, username: str, password: str):
    conn = get_db()
    cur = conn.cursor()
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    cur.execute(
        """
        INSERT INTO web_users (telegram_id, username, password_hash)
        VALUES (?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
          username = excluded.username,
          password_hash = excluded.password_hash
        """,
        (telegram_id, username, pw_hash),
    )
    conn.commit()
    conn.close()



@router.message(Command("web_login"))
async def cmd_web_login(message: Message, state: FSMContext):
    await message.answer(
        "🔐 Настройка входа на сайт.\n\n"
        "1) Придумай логин (латиница/цифры).\n"
        "2) Потом зададим пароль.\n\n"
        "Напиши желаемый логин одним сообщением:"
    )
    await state.set_state(Form.waiting_for_web_username)


@router.message(Form.waiting_for_web_username)
async def process_web_username(message: Message, state: FSMContext):
    username = message.text.strip()
    if not username or " " in username:
        await message.answer("❗ Логин не должен содержать пробелов. Попробуй ещё раз.")
        return

    await state.update_data(web_username=username)
    await message.answer(
        "Отлично! Теперь отправь пароль.\n"
        "Минимум 6 символов. Не присылай очень простой пароль 🙂"
    )
    await state.set_state(Form.waiting_for_web_password)


@router.message(Form.waiting_for_web_password)
async def process_web_password(message: Message, state: FSMContext):
    password = message.text.strip()
    if len(password) < 6:
        await message.answer("Пароль слишком короткий, нужно хотя бы 6 символов.")
        return

    data = await state.get_data()
    username = data["web_username"]
    telegram_id = message.from_user.id

    set_web_user(telegram_id, username, password)

    await message.answer(
        "✅ Готово!\n\n"
        f"Логин: <code>{username}</code>\n"
        "Теперь ты можешь войти на сайте VZALE, используя этот логин и пароль.\n"
        "Если забудешь — просто вызови /web_login ещё раз и задашь новый."
    )
    await state.clear()


async def user_exists(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        return await cursor.fetchone() is not None

async def notify_admins(text: str):
    for admin_id in ADMINS:
        try:
            await bot.send_message(chat_id=admin_id, text=text)
        except Exception as e:
            logging.warning(f"Не удалось отправить сообщение админу {admin_id}: {e}")

async def get_all_recipients():
    """Возвращает множество chat_id всех пользователей, которых мы знаем.
    Берём user_id из таблиц users и free_agents (т.к. свободные игроки могут не быть в users).
    """
    ids = set()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            async for (uid,) in cur:
                if uid:
                    ids.add(uid)
        async with db.execute("SELECT user_id FROM free_agents") as cur:
            async for (uid,) in cur:
                if uid:
                    ids.add(uid)
    # Плюс сами админы (вдруг они не в БД, но тоже хотят видеть рассылку/опрос)
    ids.update(ADMINS)
    return ids

async def ensure_tables():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("PRAGMA busy_timeout=5000;")
        # существующие таблицы опросов/идей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS polls_group (
                group_id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                options TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_closed INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS polls (
                poll_id TEXT PRIMARY KEY,
                group_id TEXT NOT NULL,
                question TEXT NOT NULL,
                options TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL
            )
        """)
                # === RATING TABLES (global + by tournament) ===
        await db.execute("""
            CREATE TABLE IF NOT EXISTS player_ratings (
                user_id INTEGER PRIMARY KEY,
                rating REAL DEFAULT 1000,
                games  INTEGER DEFAULT 0,
                updated_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS player_ratings_by_tournament (
                tournament_id INTEGER NOT NULL,
                user_id       INTEGER NOT NULL,
                rating REAL DEFAULT 1000,
                games  INTEGER DEFAULT 0,
                PRIMARY KEY (tournament_id, user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                status TEXT DEFAULT 'new',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS poll_votes (
                poll_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                option_id INTEGER NOT NULL,
                PRIMARY KEY(poll_id, user_id)
            )
        """)

        # ⚙️ Базовые таблицы (если ранее не создавались)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                team TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                team_name TEXT NOT NULL,
                member_id INTEGER NOT NULL,
                member_name TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS free_agents (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                info TEXT
            )
        """)

        # 🔐 Безопасность команды: код приглашения
        await db.execute("""
            CREATE TABLE IF NOT EXISTS team_security (
                team_name TEXT PRIMARY KEY,
                invite_code TEXT NOT NULL UNIQUE
            )
        """)
        # в ensure_tables, после CREATE TABLE
        await db.execute("PRAGMA foreign_keys=OFF;")
        cur = await db.execute("PRAGMA table_info(users)")
        cols = [r[1] async for r in cur]
        if "current_tournament_id" not in cols:
            await db.execute("ALTER TABLE users ADD COLUMN current_tournament_id INTEGER")

        # — турнирные таблицы (на случай чистой базы)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            date_start TEXT,
            venue TEXT,
            status TEXT DEFAULT 'draft',
            settings_json TEXT,
            lock_rosters_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
     

        # В ensure_tables() — ДО вставки базовых ачивок
       

        # На случай старой схемы — ALTERS (без падения, если колонка уже есть)
        try:
            await db.execute("ALTER TABLE achievements ADD COLUMN tier TEXT DEFAULT 'easy'")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE achievements ADD COLUMN order_index INTEGER DEFAULT 0")
        except Exception:
            pass

        # Связка «команда-ачивка», у тебя уже есть — оставляем
     

        # связка "команда-ачивка" уже используется в твоём коде award_achievement/list_team_achievements
        await db.execute("""
            CREATE TABLE IF NOT EXISTS team_achievements (
                team_name TEXT NOT NULL,
                tournament_id INTEGER NOT NULL,
                achievement_id INTEGER NOT NULL,
                awarded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (team_name, tournament_id, achievement_id)
        )
        """)
        # пример начального наполнения
        await db.execute("""
            INSERT OR IGNORE INTO achievements(code,emoji,title,description) VALUES
            ('FIRST_TEAM','🌟','Первый шаг','Создай или вступи в команду'),
            ('PAID_TEAM','💰','Оплачено','Команда подтвердила взнос'),
            ('FIRST_WIN','🏅','Первая победа','Победите в первом матче')
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tournament_info (
            tournament_id INTEGER NOT NULL,
            section TEXT NOT NULL,
            content TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tournament_id, section)
            )
        """)

        # кто играл за какую команду в рамках турнира
        await db.execute("""
        CREATE TABLE IF NOT EXISTS tournament_roster (
            tournament_id INTEGER NOT NULL,
            team_name     TEXT    NOT NULL,
            user_id       INTEGER NOT NULL,
            full_name     TEXT,
            is_captain    INTEGER DEFAULT 0,
            PRIMARY KEY (tournament_id, team_name, user_id)
        )
        """)

        # ачивки игроков в турнире
        await db.execute("""
        CREATE TABLE IF NOT EXISTS player_achievements (
            tournament_id  INTEGER NOT NULL,
            user_id        INTEGER NOT NULL,
            achievement_id INTEGER NOT NULL,
            awarded_at     TEXT    DEFAULT CURRENT_TIMESTAMP,
            awarded_by     INTEGER,   -- кто выдал (null = авто)
            note           TEXT,
            PRIMARY KEY (tournament_id, user_id, achievement_id)
        )
        """)

                # 🔢 Персональная статистика по матчу
        await db.execute("""
        CREATE TABLE IF NOT EXISTS player_match_stats (
            tournament_id INTEGER NOT NULL,
            match_id      INTEGER NOT NULL,
            team_name     TEXT    NOT NULL,
            user_id       INTEGER NOT NULL,
            points        INTEGER DEFAULT 0,
            threes        INTEGER DEFAULT 0,
            assists       INTEGER DEFAULT 0,
            rebounds      INTEGER DEFAULT 0,
            steals        INTEGER DEFAULT 0,
            blocks        INTEGER DEFAULT 0,
            fouls         INTEGER DEFAULT 0,
            turnovers     INTEGER DEFAULT 0,
            minutes       INTEGER DEFAULT 0,
            PRIMARY KEY (tournament_id, match_id, user_id)
        )
        """)

        # 📈 Агрегированная статистика игрока за турнир (из матчей)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS player_stats (
            tournament_id INTEGER NOT NULL,
            user_id       INTEGER NOT NULL,
            games         INTEGER DEFAULT 0,
            wins          INTEGER DEFAULT 0,
            losses        INTEGER DEFAULT 0,
            points        INTEGER DEFAULT 0,
            threes        INTEGER DEFAULT 0,
            assists       INTEGER DEFAULT 0,
            rebounds      INTEGER DEFAULT 0,
            steals        INTEGER DEFAULT 0,
            blocks        INTEGER DEFAULT 0,
            fouls         INTEGER DEFAULT 0,
            turnovers     INTEGER DEFAULT 0,
            minutes       INTEGER DEFAULT 0,
            last_updated  TEXT    DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tournament_id, user_id)
        )
        """)

        # индексы для быстрых выборок
        await db.execute("CREATE INDEX IF NOT EXISTS idx_pms_t_match ON player_match_stats(tournament_id, match_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_pms_user ON player_match_stats(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ps_user ON player_stats(user_id)")

        async def seed_achievements():
            ACHS = [
                # EASY
                ("FIRST_MATCH", "🏀", "Первый выход", "Сыграть свой первый матч.", "easy", 10),
                ("TEAM_CREATED", "👥", "Собрал команду", "Зарегистрировать команду.", "easy", 20),
                ("PAID", "💰", "Оплачено!", "Оплатить участие.", "easy", 30),
                ("FIRST_TOUR_FINISH", "🌟", "Первый шаг", "Доиграть до конца свой первый турнир.", "easy", 40),
                ("UNIFORMED", "🎉", "Мы в форме!", "Команда вышла в одинаковой форме.", "easy", 50),
                ("SWITCHED_TEAM", "👋", "Новый друг", "Сыграть с новой командой (сменить команду ≥ 1 раз).", "easy", 60),

                # MEDIUM
                ("FIRST_WIN", "🏆", "Первая победа", "Выиграть матч.", "medium", 10),
                ("WIN_STREAK3", "🔥", "Серия побед", "Выиграть 3 матча подряд.", "medium", 20),
                ("HUNDRED_POINTS", "💯", "Сто очков", "Набрать 100 очков суммарно.", "medium", 30),
                ("IRON_DEFENSE", "🧱", "Железная защита", "Пропустить < 10 очков за матч.", "medium", 40),
                ("TEN_GAMES", "⛹️", "Опытные", "Сыграть 10 матчей.", "medium", 50),
                ("SNIPER", "🎯", "Снайпер", "5 трёхочковых за турнир.", "medium", 60),
                ("WIN_BY_10", "⚡", "Молниеносный", "Победа с отрывом ≥ 10 очков.", "medium", 70),
                ("NO_SUBS_TOUR", "🏋️", "Железный", "Сыграть турнир без замен.", "medium", 80),
                ("ASSISTS10", "🦸", "Командный игрок", "10 результативных передач в турнире.", "medium", 90),
                ("ANKLEBREAKER", "🐍", "Анклбрейкер", "Эффектный кроссовер (выдаётся судьёй).", "medium", 100),
                ("TOP3", "🥈", "Призёр", "Войти в топ-3 турнира.", "medium", 110),

                # HARD
                ("CHAMPION", "🥇", "Чемпион", "Выиграть турнир.", "hard", 10),
                ("DOUBLE_CHAMP", "🏅", "Дважды чемпион", "Выиграть 2 турнира.", "hard", 20),
                ("VZ_LEGEND", "👑", "Легенда VZALE", "Выиграть 5 турниров.", "hard", 30),
                ("6_TOURS_STREAK", "🌍", "Всегда в игре", "Поучаствовать в 6 турнирах подряд.", "hard", 40),
                ("BETTER_NEXT", "📈", "Прогресс", "Улучшить результат команды на следующем турнире.", "hard", 50),
                ("FIFTY_GAMES", "🧮", "Статист", "Сыграть 50 матчей.", "hard", 60),
                ("TEN_TOURS", "🚀", "Старожил", "Принять участие в 10 турнирах.", "hard", 70),
                ("NO_MISS_3_TOURS", "🕒", "Нон-стоп", "Провести 3 турнира подряд без пропуска.", "hard", 80),
                ("HIGHLIGHT", "🎤", "Звезда вечера", "Попасть в хайлайт турнира (выбирается организаторами).", "hard", 90),

                # ULTRA
                ("GRAND_SLAM", "🏆", "Grand Slam", "Выиграть финал сухо (например, 21:0).", "ultra", 10),
                ("MVP", "🕹", "MVP", "Признан MVP турнира.", "ultra", 20),
                ("UNDEFEATED_TOUR", "🔥", "Бессмертные", "Команда не проиграла ни одного матча за турнир.", "ultra", 30),
                ("DYNASTY3", "⚔️", "Династия", "Одна и та же команда выигрывает 3 турнира подряд.", "ultra", 40),
                ("2V3_WIN", "🐺", "Одиночка", "Сыграть хотя бы один матч 2×3 и победить.", "ultra", 50),
                ("CAPTAIN5", "🎖", "Командир", "Сыграть капитаном 5 турниров подряд.", "ultra", 60),

                # ULTIMATE GOAL — как «мета-ачивка»
                ("ULT_GOAL", "🥶", "VZALE Champion", "Собрать все ачивки и получить уникальный лонгслив.", "ultimate", 999),
            ]
            # UPSERT сидов
            await db.executemany("""
                INSERT INTO achievements(code, emoji, title, description, tier, order_index)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(code) DO UPDATE SET
                    emoji=excluded.emoji,
                    title=excluded.title,
                    description=excluded.description,
                    tier=excluded.tier,
                    order_index=excluded.order_index
            """, ACHS)
        await seed_achievements()



        await db.commit()

from aiogram.fsm.state import StatesGroup, State

class AchGrantGlobal(StatesGroup):
    user = State()
    ach = State()


async def main():
    logging.basicConfig(level=logging.INFO)
    logging.info("⏳ Инициализация БД...")
    await ensure_tables()
    logging.info("✅ Таблицы готовы")
    await backfill_team_codes()
    logging.info("✅ Коды команд обновлены")
    logging.info("🚀 Запуск поллинга...")
    await dp.start_polling(bot)

async def get_achievement_id_by_code(code: str) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id FROM achievements WHERE code=?", (code,))
        row = await cur.fetchone()
        return row[0] if row else None

@router.callback_query(F.data == "ach_admin_global")
async def ach_admin_global_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    await state.set_state(AchGrantGlobal.user)
    await cb.message.edit_text("Введи ID пользователя (числом) или перешли любое его сообщение сюда.")
    await cb.answer()

@router.message(AchGrantGlobal.user)
async def ach_admin_global_pick_user(msg: Message, state: FSMContext):
    uid = None
    if msg.forward_from:
        uid = msg.forward_from.id
    else:
        try:
            uid = int(msg.text.strip())
        except Exception:
            await msg.answer("Нужен числовой ID или форвард сообщения пользователя."); return

    # список ачивок, которых ещё нет за всё время
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT a.code, COALESCE(a.emoji,'')||' '||a.title
            FROM achievements a
            WHERE NOT EXISTS(
                SELECT 1 FROM player_achievements pa
                WHERE pa.user_id=? AND pa.achievement_id=a.id
            )
            ORDER BY CASE a.tier
                WHEN 'easy' THEN 1 WHEN 'medium' THEN 2 WHEN 'hard' THEN 3
                WHEN 'ultra' THEN 4 WHEN 'ultimate' THEN 5 ELSE 9 END,
                a.order_index, a.title COLLATE NOCASE
        """, (uid,))
        opts = await cur.fetchall()

    if not opts:
        await msg.answer("У пользователя уже есть все ачивки 🙂"); 
        await state.clear()
        return

    await state.update_data(uid=uid)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=title, callback_data=f"ach_admin_global_grant:{code}")]
        for code, title in opts
    ] + [[InlineKeyboardButton(text="🚫 Отмена", callback_data="ach_admin_cancel")]])
    await state.set_state(AchGrantGlobal.ach)
    await msg.answer(f"Кому: <code>{uid}</code>\nВыбери ачивку для выдачи:", reply_markup=kb)


async def award_player_achievement(tournament_id: int | None, user_id: int, code: str,
                                   awarded_by: int | None = None, note: str | None = None) -> bool:
    tid = tournament_id if tournament_id is not None else GLOBAL_TOURNAMENT_ID
    ach_id = await get_achievement_id_by_code(code)
    if not ach_id:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("""
                INSERT INTO player_achievements(tournament_id, user_id, achievement_id, awarded_by, note)
                VALUES(?,?,?,?,?)
            """, (tid, user_id, ach_id, awarded_by, note))
            await db.commit()
            return True
        except Exception:
            return False


async def revoke_player_achievement(tournament_id: int, user_id: int, code: str) -> bool:
    ach_id = await get_achievement_id_by_code(code)
    if not ach_id:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            DELETE FROM player_achievements
            WHERE tournament_id=? AND user_id=? AND achievement_id=?
        """, (tournament_id, user_id, ach_id))
        await db.commit()
        return cur.rowcount > 0

async def roster_users(tournament_id: int, team_name: str) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT user_id FROM tournament_roster
            WHERE tournament_id=? AND team_name=?
        """, (tournament_id, team_name))
        rows = await cur.fetchall()
    return [r[0] for r in rows]

async def award_team_and_players(team_name: str, tournament_id: int, code: str,
                                 awarded_by: int | None = None):
    # 1) командная запись (как у тебя было)
    award_achievement(team_name, tournament_id, code)  # порядок аргументов как в твоей функции! :contentReference[oaicite:8]{index=8}
    # 2) всем игрокам в ростере
    for uid in await roster_users(tournament_id, team_name):
        await award_player_achievement(tournament_id, uid, code, awarded_by=awarded_by)

@router.callback_query(F.data.startswith("ach_admin_global_grant:"))
async def ach_admin_global_grant(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    code = cb.data.split(":",1)[1]
    data = await state.get_data()
    uid = data.get("uid")
    ok = await award_player_achievement(None, uid, code, awarded_by=cb.from_user.id, note="global")
    await cb.answer("Выдано ✅" if ok else "Уже было", show_alert=False)
    await state.clear()

async def backfill_global_from_existing() -> int:
    """
    Берёт все player_achievements с tournament_id <> 0 и добавляет такие же записи с tournament_id = 0,
    если их ещё нет. Возвращает, сколько строк добавили.
    """
    added = 0
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT DISTINCT pa.user_id, pa.achievement_id
            FROM player_achievements pa
            WHERE pa.tournament_id <> 0
              AND NOT EXISTS(
                    SELECT 1 FROM player_achievements g
                    WHERE g.tournament_id = 0
                      AND g.user_id = pa.user_id
                      AND g.achievement_id = pa.achievement_id
              )
        """)
        rows = await cur.fetchall()
        for uid, ach_id in rows:
            try:
                await db.execute("""
                    INSERT INTO player_achievements(tournament_id, user_id, achievement_id)
                    VALUES(0, ?, ?)
                """, (uid, ach_id))
                added += 1
            except Exception:
                pass
        await db.commit()
    return added


import aiosqlite, time

# нормализуем значения (защита от None/отрицательных)
def _nz(x): 
    try: 
        v = int(x or 0)
        return v if v >= 0 else 0
    except: 
        return 0

async def upsert_player_match_stats(
    tid: int, match_id: int, team_name: str, user_id: int,
    *, points=0, threes=0, assists=0, rebounds=0, steals=0, blocks=0, fouls=0, turnovers=0, minutes=0
) -> None:
    p = _nz(points); t=_nz(threes); a=_nz(assists); r=_nz(rebounds)
    s=_nz(steals); b=_nz(blocks); f=_nz(fouls); to=_nz(turnovers); m=_nz(minutes)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        await db.execute("""
            INSERT INTO player_match_stats(tournament_id, match_id, team_name, user_id,
                                           points, threes, assists, rebounds, steals, blocks, fouls, turnovers, minutes)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(tournament_id, match_id, user_id) DO UPDATE SET
                team_name=excluded.team_name,
                points=excluded.points, threes=excluded.threes, assists=excluded.assists,
                rebounds=excluded.rebounds, steals=excluded.steals, blocks=excluded.blocks,
                fouls=excluded.fouls, turnovers=excluded.turnovers, minutes=excluded.minutes
        """, (tid, match_id, team_name, user_id, p, t, a, r, s, b, f, to, m))
        await db.commit()


async def recalc_player_stats_for_tournament(tid:int, user_id:int|None=None):

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        # остальной код как у тебя, но в выборках добавь фильтр:
        # WHERE tournament_id=? AND (user_id=? OR ? IS NULL)

        # кого пересчитывать
        if user_id is None:
            cur = await db.execute("""
                SELECT DISTINCT user_id FROM player_match_stats WHERE tournament_id=?
            """, (tid,))
            uids = [r[0] for r in await cur.fetchall()]
        else:
            uids = [user_id]

        # кеш побед/поражений по матчам для каждого игрока
        # считаем winner из matches_simple
        curm = await db.execute("""
            SELECT id, team_home_name, team_away_name, score_home, score_away
            FROM matches_simple WHERE tournament_id=? AND status='finished'
        """, (tid,))
        matches = await curm.fetchall()
        winners = {}
        for mid, h, a, sh, sa in matches:
            if sh == sa: 
                continue
            winners[mid] = (h if sh > sa else a)

        for uid in uids:
            # суммируем по матчам игрока
            cur = await db.execute("""
                SELECT p.match_id, p.team_name,
                    p.points, p.threes, p.assists, p.rebounds, p.steals, p.blocks, p.fouls, p.turnovers, p.minutes
                FROM player_match_stats p
                WHERE p.tournament_id=? AND p.user_id=?
            """, (tid, uid))
            rows = await cur.fetchall()

            games = len(rows)
            wins = sum(1 for mid, team, *_ in rows if mid in winners and winners[mid] == team)
            losses = sum(1 for mid, team, *_ in rows if mid in winners and winners[mid] != team)

            # totals должны быть ровно 9 чисел:
            totals = [0,0,0,0,0,0,0,0,0]  # points, threes, assists, rebounds, steals, blocks, fouls, turnovers, minutes
            for _, _, pts, thr, ast, reb, stl, blk, fls, tov, min_ in rows:
                totals[0]+= _nz(pts); totals[1]+=_nz(thr); totals[2]+=_nz(ast); totals[3]+=_nz(reb)
                totals[4]+=_nz(stl); totals[5]+=_nz(blk); totals[6]+=_nz(fls); totals[7]+=_nz(tov); totals[8]+=_nz(min_)

            await db.execute("""
                INSERT INTO player_stats(tournament_id, user_id, games, wins, losses,
                                        points, threes, assists, rebounds, steals, blocks, fouls, turnovers, minutes, last_updated)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
                ON CONFLICT(tournament_id, user_id) DO UPDATE SET
                    games=excluded.games, wins=excluded.wins, losses=excluded.losses,
                    points=excluded.points, threes=excluded.threes, assists=excluded.assists,
                    rebounds=excluded.rebounds, steals=excluded.steals, blocks=excluded.blocks,
                    fouls=excluded.fouls, turnovers=excluded.turnovers, minutes=excluded.minutes,
                    last_updated=datetime('now')
            """, (tid, uid, games, wins, losses, *totals))

        await db.commit()


@router.callback_query(F.data == "ach_admin_cancel")
async def ach_admin_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer("Отменено", show_alert=False)


async def ensure_team_code(team_name: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT invite_code FROM team_security WHERE team_name=?", (team_name,))
        row = await cur.fetchone()
        if row and row[0]:
            return row[0]

        # нет кода — создаём
        code = gen_invite_code(6)
        unique = False
        attempts = 0
        while not unique and attempts < 10:
            try:
                await db.execute("INSERT INTO team_security (team_name, invite_code) VALUES (?, ?)", (team_name, code))
                await db.commit()
                unique = True
            except Exception:
                code = gen_invite_code(6)
                attempts += 1
        return code

# Общая утилита экранирования под MarkdownV2
def esc_md2(s: str) -> str:
  
    if s is None:
        return ""
    # Сначала экранируем обратный слеш
    s = s.replace("\\", "\\\\")
    specials = r"_*[]()~`>#+-=|{}.!".split()
    # .split() вернет один элемент строку; лучше просто пройти по строке:
    for ch in r"_*[]()~`>#+-=|{}.!":
        s = s.replace(ch, "\\" + ch)
    return s


async def backfill_team_codes():
    async with aiosqlite.connect(DB_PATH) as db:
        # все команды, у которых есть участники
        cur = await db.execute("SELECT DISTINCT team_name FROM teams")
        team_rows = await cur.fetchall()
        if not team_rows:
            return
        # уже имеющие код
        cur = await db.execute("SELECT team_name FROM team_security")
        secured = {r[0] for r in await cur.fetchall()}

    # создаём коды только тем, у кого их нет
    for (team_name,) in team_rows:
        if team_name and team_name not in secured:
            await ensure_team_code(team_name)
            await asyncio.sleep(0.1)


    # ==== TOURNAMENT DB HELPERS ====

def db():

    return sqlite3.connect("tournament.db")

def get_tournaments(active_only=False):
    with db() as con:
        if active_only:
            return con.execute(
                "SELECT id, name, status FROM tournaments WHERE status IN ('announced','registration_open','running') ORDER BY id DESC"
            ).fetchall()
        return con.execute(
            "SELECT id, name, status FROM tournaments ORDER BY id DESC"
        ).fetchall()

# ==== STATS HELPERS ====
def tt_list_names(tid:int):
    with db() as con:
        return [r[0] for r in con.execute(
            "SELECT name FROM tournament_team_names WHERE tournament_id=? ORDER BY name COLLATE NOCASE",
            (tid,)
        ).fetchall()]

def tt_toggle_paid(tid:int, name:str) -> int:
    """Переключает статус оплаты: 0→1, 1→0. Возвращает новое значение."""
    with db() as con:
        cur = con.execute("SELECT paid FROM tournament_team_names WHERE tournament_id=? AND name=?", (tid, name)).fetchone()
        if not cur: return -1
        new_val = 0 if cur[0] else 1
        con.execute("UPDATE tournament_team_names SET paid=? WHERE tournament_id=? AND name=?", (new_val, tid, name))
        con.commit()
        return new_val



def tt_get_paid(tid:int, name:str) -> int:
    with db() as con:
        row = con.execute("SELECT paid FROM tournament_team_names WHERE tournament_id=? AND name=?", (tid, name)).fetchone()
        return row[0] if row else 0


def tt_add_name(tid:int, name:str)->bool:
    name = (name or "").strip()
    if not name: return False
    with db() as con:
        try:
            con.execute("INSERT INTO tournament_team_names(tournament_id,name) VALUES(?,?)", (tid, name))
            con.commit()
            return True
        except Exception:
            return False

def tt_delete_name(tid:int, name:str)->int:
    with db() as con:
        cur = con.execute("DELETE FROM tournament_team_names WHERE tournament_id=? AND name=?", (tid, name))
        con.commit()
        return cur.rowcount

# ==== PAYMENT HELPERS ====
def team_get_paid(tid:int, team_name:str) -> int:
    with db() as con:
        row = con.execute(
            "SELECT paid FROM tournament_team_names WHERE tournament_id=? AND name=?",
            (tid, team_name)
        ).fetchone()
        return row[0] if row else 0

def player_get_paid(user_id:int, tid:int) -> int:
    with db() as con:
        row = con.execute(
            "SELECT paid FROM player_payments WHERE user_id=? AND tournament_id=?",
            (user_id, tid)
        ).fetchone()
        return row[0] if row else 0


def team_toggle_paid(tid:int, name:str) -> int:
    with db() as con:
        cur = con.execute("SELECT paid FROM tournament_team_names WHERE tournament_id=? AND name=?", (tid,name)).fetchone()
        if not cur: return -1
        new_val = 0 if cur[0] else 1
        con.execute("UPDATE tournament_team_names SET paid=? WHERE tournament_id=? AND name=?", (new_val, tid, name))
        con.commit()
        return new_val

def team_get_paid(tid:int, name:str) -> int:
    with db() as con:
        row = con.execute("SELECT paid FROM tournament_team_names WHERE tournament_id=? AND name=?", (tid,name)).fetchone()
        return row[0] if row else 0

def player_toggle_paid(user_id:int, tid:int) -> int:
    with db() as con:
        row = con.execute(
            "SELECT paid FROM player_payments WHERE user_id=? AND tournament_id=?",
            (user_id, tid)
        ).fetchone()
        new_val = 0 if (row and row[0]) else 1
        con.execute(
            "INSERT INTO player_payments(user_id, tournament_id, paid) VALUES(?,?,?) "
            "ON CONFLICT(user_id, tournament_id) DO UPDATE SET paid=excluded.paid",
            (user_id, tid, new_val)
        )
        con.commit()
        return new_val

def player_get_paid(user_id:int, tid:int) -> int:
    with db() as con:
        row = con.execute(
            "SELECT paid FROM player_payments WHERE user_id=? AND tournament_id=?",
            (user_id, tid)
        ).fetchone()
        return row[0] if row else 0


def ms_add_match(tid:int, home:str, away:str, stage:str|None):
    with db() as con:
        con.execute("""INSERT INTO matches_simple(tournament_id, stage, team_home_name, team_away_name, status)
                       VALUES(?,?,?,?, 'scheduled')""", (tid, stage, home, away))
        con.commit()

def ms_list_matches(tid:int, only_open:bool=False, limit:int=50):
    with db() as con:
        if only_open:
            return con.execute("""SELECT id, stage, team_home_name, team_away_name, score_home, score_away, status
                                  FROM matches_simple
                                  WHERE tournament_id=? AND status='scheduled'
                                  ORDER BY id DESC LIMIT ?""", (tid, limit)).fetchall()
        return con.execute("""SELECT id, stage, team_home_name, team_away_name, score_home, score_away, status
                              FROM matches_simple
                              WHERE tournament_id=?
                              ORDER BY id DESC LIMIT ?""", (tid, limit)).fetchall()

def ms_save_score(match_id:int, sh:int, sa:int):
    with db() as con:
        con.execute("UPDATE matches_simple SET score_home=?, score_away=?, status='finished' WHERE id=?",
                    (sh, sa, match_id))
        con.commit()

def ms_delete_match(match_id:int):
    with db() as con:
        con.execute("DELETE FROM matches_simple WHERE id=?", (match_id,))
        con.commit()

def ms_last_results(tid:int, n:int=5):
    with db() as con:
        return con.execute("""SELECT team_home_name, score_home, score_away, team_away_name, stage
                              FROM matches_simple
                              WHERE tournament_id=? AND status='finished'
                              ORDER BY id DESC LIMIT ?""", (tid, n)).fetchall()

def standings_for_tournament(tid:int):
    SQL = """
    WITH rows AS (
        SELECT team_home_name AS team, score_home AS pf, score_away AS pa
        FROM matches_simple WHERE tournament_id=? AND status='finished'
        UNION ALL
        SELECT team_away_name AS team, score_away AS pf, score_home AS pa
        FROM matches_simple WHERE tournament_id=? AND status='finished'
    )
    SELECT team,
           COUNT(*) AS games,
           SUM(CASE WHEN pf>pa THEN 1 ELSE 0 END) AS wins,
           SUM(CASE WHEN pf<pa THEN 1 ELSE 0 END) AS losses,
           COALESCE(SUM(pf),0) AS pf,
           COALESCE(SUM(pa),0) AS pa,
           COALESCE(SUM(pf-pa),0) AS diff
    FROM rows
    GROUP BY team
    ORDER BY wins DESC, diff DESC, pf DESC, team COLLATE NOCASE ASC;
    """
    with db() as con:
        return con.execute(SQL, (tid, tid)).fetchall()


def get_tournament_by_id(tid:int):
    with db() as con:
        return con.execute(
            "SELECT id, name, status FROM tournaments WHERE id=?", (tid,)
        ).fetchone()

def set_user_current_tournament(user_id:int, tournament_id:int):
    with db() as con:
        con.execute("UPDATE users SET current_tournament_id=? WHERE user_id=?", (tournament_id, user_id))
        if con.total_changes == 0:
            con.execute("INSERT OR IGNORE INTO users(user_id, full_name, current_tournament_id) VALUES(?, ?, ?)",
                        (user_id, "", tournament_id))
        con.commit()

def get_user_current_tournament(user_id:int):
    with db() as con:
        row = con.execute("SELECT current_tournament_id FROM users WHERE user_id=?", (user_id,)).fetchone()
        return row[0] if row else None

def get_or_default_tournament(user_id:int):
    tid = get_user_current_tournament(user_id)
    if tid:
        return tid
    tours = get_tournaments(active_only=True)
    if tours:
        tid = tours[0][0]
        set_user_current_tournament(user_id, tid)
        return tid
    return None

# Разделы информации турнира
SECTIONS = [
    ("about",    "О турнире"),
    ("rules",    "Правила"),
    ("schedule", "Расписание"),
    ("brackets", "Сетка"),
    ("map",      "Локация"),
    ("contacts", "Контакты"),
    ("faq",      "FAQ"),
]

# === UNIVERSAL SBP LINK ===
PAY_LINK = "https://www.tinkoff.ru/rm/r_lXNVlLdhlc.HvLpSfyoBm/lp4m185877"


def kb_admin_team_payment(tid:int, team_name:str, players:list):
    rows = []
    team_paid = team_get_paid(tid, team_name)
    rows.append([InlineKeyboardButton(
        text=f"💰 Командный взнос: {'✅' if team_paid else '❌'}",
        callback_data=f"admin_pay_team:{tid}:{team_name}"
    )])
    for (uid, uname, paid) in players:
        rows.append([InlineKeyboardButton(
            text=f"{'✅' if paid else '❌'} {uname}",
            callback_data=f"admin_pay_player:{tid}:{uid}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_tt:{tid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_tinfo_sections(tid:int):
    rows = [[InlineKeyboardButton(text=title, callback_data=f"t_info_show:{tid}:{key}")]
            for key, title in SECTIONS]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"open_tournament:{tid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)



# ==== GLOBAL & TOURNAMENT MENUS ====

def kb_global(user_id: int):
    tours = get_tournaments(active_only=True)

    rows = [
        [InlineKeyboardButton(text="🏆 Выбрать турнир", callback_data="choose_tournament")]
    ]

       # ← НОВОЕ: приоритетный турнир
    pt = get_priority_tournament()
    if pt:
        rows.append([InlineKeyboardButton(
            text=f"🎟 Регистрация на {pt[1]}",
            callback_data=f"open_tournament:{pt[0]}"
        )])

    rows.append([InlineKeyboardButton(text="💡 Идеи/ошибки", callback_data="suggest_feature")])
    rows.append([InlineKeyboardButton(text="🏆 Все ачивки", callback_data="achievements_all")])
    rows.append([InlineKeyboardButton(text="🎖 Мои ачивки", callback_data="t_myach_all")])
    rows.append([InlineKeyboardButton(text="📈 Моя статистика", callback_data="my_stats_global")])
    rows.append([InlineKeyboardButton(text="🏆 Топ-игроки", callback_data="rating_top")])


    """
    rows += [
        [InlineKeyboardButton(text="📋 Мои регистрации", callback_data="my_regs")],
        [InlineKeyboardButton(text="🧾 Мои команды", callback_data="my_teams")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="🧑‍🚀 Свободные агенты", callback_data="free_agents_menu")],
        [InlineKeyboardButton(text="ℹ️ FAQ/Правила", callback_data="faq")]
    ]
    """
    if user_id in ADMINS:
        rows.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_tournaments")])

    return InlineKeyboardMarkup(inline_keyboard=rows)

# === MY STATS (global / last tournament) ===
def _kb_stats_scope():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="За всё время", callback_data="my_stats_scope:global"),
         InlineKeyboardButton(text="Последний турнир", callback_data="my_stats_scope:last")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_global")]
    ])

async def _last_finished_tournament_id():
    async with aiosqlite.connect(DB_PATH) as db:
        # считаем "последним" любой турнир с finished/archived/running по убыв. id; приоритет: archived→running
        cur = await db.execute("SELECT id FROM tournaments WHERE status IN ('archived','running') ORDER BY (status='archived') DESC, id DESC LIMIT 1")
        row = await cur.fetchone()
        if row: return row[0]
        cur = await db.execute("SELECT id FROM tournaments ORDER BY id DESC LIMIT 1")
        row = await cur.fetchone()
        return row[0] if row else None

async def _render_my_stats(uid: int, scope: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        # имя
        cur = await db.execute("SELECT COALESCE(full_name,''), COALESCE(team,'') FROM users WHERE user_id=?", (uid,))
        u = await cur.fetchone()
        full_name = u[0] if u else str(uid)

        if scope == "global":
            # рейтинг из player_ratings, а счётчики суммируем по player_stats
            cur = await db.execute("SELECT rating, games FROM player_ratings WHERE user_id=?", (uid,))
            r = await cur.fetchone()
            rating = round(r[0], 1) if r else 1000.0
            games = r[1] if r else 0

            agg = await db.execute("""
                SELECT COALESCE(SUM(points),0), COALESCE(SUM(assists),0), COALESCE(SUM(blocks),0),
                       COALESCE(SUM(wins),0), COALESCE(SUM(losses),0)
                FROM player_stats WHERE user_id=?
            """, (uid,))
            p,a,b,w,l = await agg.fetchone() or (0,0,0,0,0)
            caption = "За всё время"
        else:
            tid = await _last_finished_tournament_id()
            if not tid:
                return "Пока нет завершённых турниров."
            cur = await db.execute("""
                SELECT rating, games FROM player_ratings_by_tournament WHERE tournament_id=? AND user_id=?
            """, (tid, uid))
            r = await cur.fetchone()
            rating = round(r[0], 1) if r else 1000.0
            games = r[1] if r else 0

            agg = await db.execute("""
                SELECT COALESCE(points,0), COALESCE(assists,0), COALESCE(blocks,0),
                       COALESCE(wins,0), COALESCE(losses,0)
                FROM player_stats WHERE tournament_id=? AND user_id=?
            """, (tid, uid))
            row = await agg.fetchone()
            p,a,b,w,l = row if row else (0,0,0,0,0)
            caption = "Последний турнир"

    return (
        f"📈 <b>Моя статистика — {caption}</b>\n"
        f"👤 {html.escape(full_name)}\n"
        f"🎮 Матчей: {games}\n"
        f"⭐ Рейтинг: {rating}\n"
        f"🏀 Очки: {p}   🎯 Ассисты: {a}   🧱 Блоки: {b}\n"
        f"✅ Побед: {w}   ❌ Поражений: {l}"
    )

@router.callback_query(F.data == "my_stats_global")
async def my_stats_global(cb: CallbackQuery):
    text = await _render_my_stats(cb.from_user.id, "global")
    await cb.message.edit_text(text, reply_markup=_kb_stats_scope(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("my_stats_scope:"))
async def my_stats_scope(cb: CallbackQuery):
    scope = cb.data.split(":")[1]  # global | last
    text = await _render_my_stats(cb.from_user.id, scope)
    await cb.message.edit_text(text, reply_markup=_kb_stats_scope(), parse_mode="HTML")
    await cb.answer()

# === RATING TOP ===
def _kb_rating_scope():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="За всё время", callback_data="rating_scope:global"),
         InlineKeyboardButton(text="Последний турнир", callback_data="rating_scope:last")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_global")]
    ])

def _render_top_rows(rows, title):
    if not rows:
        return f"🏆 {title}\nПока пусто."
    lines = [f"🏆 {title}"]
    for i, (uname, rating, games) in enumerate(rows, start=1):
        tag = f"@{uname}" if uname else "—"
        lines.append(f"{i}) {tag} — {round(rating,1)} RP (игр: {games})")
    return "\n".join(lines)

@router.callback_query(F.data == "rating_top")
async def rating_top(cb: CallbackQuery):
    # глобально по player_ratings
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT COALESCE(u.full_name, '—') AS display_name, r.rating, r.games
            FROM player_ratings r
            LEFT JOIN users u ON u.user_id = r.user_id
            ORDER BY r.rating DESC
            LIMIT 10
        """)
        rows = await cur.fetchall()
    await cb.message.edit_text(_render_top_rows(rows, "ТОП-10 (за всё время)"),
                               reply_markup=_kb_rating_scope(), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("rating_scope:"))
async def rating_scope(cb: CallbackQuery):
    scope = cb.data.split(":")[1]
    if scope == "global":
        await rating_top(cb); return
    # last tournament
    tid = await _last_finished_tournament_id()
    if not tid:
        await cb.message.edit_text("Пока нет завершённых турниров.", reply_markup=_kb_rating_scope()); await cb.answer(); return
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("""
                SELECT COALESCE(u.full_name, '—') AS display_name, r.rating, r.games
                FROM player_ratings_by_tournament r
                LEFT JOIN users u ON u.user_id = r.user_id
                WHERE r.tournament_id = ?
                ORDER BY r.rating DESC
                LIMIT 10
            """, (tid,))
            rows = await cur.fetchall()
        await cb.message.edit_text(_render_top_rows(rows, "ТОП-10 (последний турнир)"),
                                reply_markup=_kb_rating_scope(), parse_mode="HTML")
        await cb.answer()



@router.callback_query(F.data == "suggest_feature")
async def suggest_feature_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text(
        "Опиши идею или проблему одним сообщением.\n"
        "Можно приложить ссылки. Спасибо! 🙌"
    )
    await state.set_state(SuggestionForm.waiting_text)
    await cb.answer()

@router.callback_query(F.data == "t_myach_all")
async def t_my_achievements_all(cb: CallbackQuery):
    uid = cb.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT a.code, COALESCE(a.emoji,'•'), a.title, a.tier,
                   EXISTS(
                       SELECT 1 FROM player_achievements pa
                       WHERE pa.user_id=? AND pa.achievement_id=a.id
                   ) AS done
            FROM achievements a
            ORDER BY CASE a.tier
                WHEN 'easy' THEN 1 WHEN 'medium' THEN 2 WHEN 'hard' THEN 3
                WHEN 'ultra' THEN 4 WHEN 'ultimate' THEN 5 ELSE 9 END,
                a.order_index, a.title COLLATE NOCASE
        """, (uid,))
        rows = await cur.fetchall()

    groups = {
        "easy": "🎯 *EASY*", "medium": "⚡ *MEDIUM*", "hard": "👑 *HARD*",
        "ultra":"💎 *ULTRA*", "ultimate":"👕 *ULTIMATE GOAL*"
    }

    done_cnt = sum(1 for r in rows if r[4])
    total = len(rows)
    lines = [f"🎖 *Мои ачивки* · за всё время", f"Прогресс: *{done_cnt}/{total}*", ""]
    last = None
    for _, emoji, title, tier, done in rows:
        if tier != last:
            if last is not None: lines.append("")
            lines.append(groups.get(tier, f"*{tier.upper()}*"))
            last = tier
        check = "✅" if done else "⬜️"
        lines.append(f"{check} {emoji} *{esc_md2(title)}*")

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_global")]
    ])
    await cb.message.edit_text(text, parse_mode="MarkdownV2", reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("t_myach:"))
async def t_my_achievements(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    uid = cb.from_user.id

    # все ачивки с пометкой выполнено/нет
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT a.code, COALESCE(a.emoji,'•'), a.title, a.tier,
                   CASE WHEN pa.user_id IS NULL THEN 0 ELSE 1 END AS done
            FROM achievements a
            LEFT JOIN player_achievements pa
              ON pa.achievement_id = a.id AND pa.tournament_id=? AND pa.user_id=?
            ORDER BY CASE a.tier
                WHEN 'easy' THEN 1 WHEN 'medium' THEN 2 WHEN 'hard' THEN 3
                WHEN 'ultra' THEN 4 WHEN 'ultimate' THEN 5 ELSE 9 END,
                a.order_index, a.title COLLATE NOCASE
        """, (tid, uid))
        rows = await cur.fetchall()

    # рендер
    groups = {"easy": "🎯 *EASY*", "medium": "⚡ *MEDIUM*", "hard": "👑 *HARD*", "ultra": "💎 *ULTRA*", "ultimate": "👕 *ULTIMATE GOAL*"}
    lines = [f"🎖 *Мои ачивки* · турнир *{esc_md2(get_tournament_by_id(tid)[1])}*", ""]
    last_tier = None
    done_cnt = 0
    total = len(rows)
    for code, emoji, title, tier, done in rows:
        if tier != last_tier:
            if last_tier is not None: lines.append("")
            lines.append(groups.get(tier, f"*{tier.upper()}*"))
            last_tier = tier
        check = "✅" if done else "⬜️"
        if done: done_cnt += 1
        lines.append(f"{check} {emoji} *{esc_md2(title)}*")

    lines.insert(1, f"Прогресс: *{done_cnt}/{total}*")
    text = "\n".join(lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к турниру", callback_data=f"open_tournament:{tid}")]
    ])
    await cb.message.edit_text(text, parse_mode="MarkdownV2", reply_markup=kb)
    await cb.answer()


@router.message(SuggestionForm.waiting_text)
async def suggest_feature_save(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if not txt:
        await message.answer("Пустое сообщение. Введи текст идеи/багрепорта 🙏")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO suggestions(user_id, text) VALUES(?,?)",
            (message.from_user.id, txt)
        )
        await db.commit()
    await state.clear()
    await message.answer("✅ Спасибо! Мы получили твоё сообщение.")


def kb_pick_team_public(tid:int):
    names = tt_list_names(tid)
    rows, row = [], []
    for name in names:
        row.append(InlineKeyboardButton(text=name, callback_data=f"t_team:{tid}:{name}"))
        if len(row)==2:
            rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"t_stats_menu:{tid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_tournaments_list():
    tours = get_tournaments(active_only=True)
    rows = [
        [InlineKeyboardButton(text=f"{t[1]} · {t[2]}", callback_data=f"open_tournament:{t[0]}")]
        for t in tours
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_global")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# === MENU: TOURNAMENT (CONDITIONAL) ===
def kb_tournament_menu(tid: int, user_id: int):
    with db() as con:
        r = con.execute("SELECT team FROM users WHERE user_id=?", (user_id,)).fetchone()
        team = r[0] if r and r[0] else None
        in_team = bool(team)
        is_free = bool(con.execute("SELECT 1 FROM free_agents WHERE user_id=?", (user_id,)).fetchone())

    rows = []
    rows.append([InlineKeyboardButton(text="ℹ️ Информация о турнире", callback_data=f"t_info:{tid}")])

    if not in_team:
        rows.append([InlineKeyboardButton(text="👤 Я капитан — зарегистрировать команду", callback_data=f"t_register_team:{tid}")])
        rows.append([InlineKeyboardButton(text="🔑 Присоединиться по коду", callback_data=f"t_join:{tid}")])
        if not is_free:
            rows.append([InlineKeyboardButton(text="🧑‍🚀 Стать свободным игроком", callback_data=f"t_free:{tid}")])

    rows.append([InlineKeyboardButton(text="👥 Моя команда (этот турнир)", callback_data=f"t_myteam:{tid}")])

    if in_team:
        """ rows.append([InlineKeyboardButton(text="💳 Оплатить взнос", callback_data=f"t_pay:{tid}")])"""
        rows.append([InlineKeyboardButton(text="🚪 Выйти из команды", callback_data=f"t_leave:{tid}")])

    rows += [
        [InlineKeyboardButton(text="📊 Статистика", callback_data=f"t_stats_menu:{tid}")],
        [InlineKeyboardButton(text="⬅️ К списку турниров", callback_data="choose_tournament")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_global")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)




def kb_pay_menu(tid: int, team_size: int | None):
    # считаем сумму для команды
    team_amount = None
    team_line = None
    if team_size is not None and team_size > 0:
        team_amount = TEAM_FEE_3 if team_size <= 3 else TEAM_FEE_4PLUS
        team_line = f"👥 За команду — {team_amount} ₽ ({team_size} игрок.)"

    rows = [
        [InlineKeyboardButton(text=f"🧑 За игрока — {PLAYER_FEE} ₽", callback_data=f"t_pay_player:{tid}")],
    ]
    if team_line:
        rows.append([InlineKeyboardButton(text=team_line, callback_data=f"t_pay_team:{tid}")])

    rows.append([InlineKeyboardButton(text="⬅️ Назад к турниру", callback_data=f"open_tournament:{tid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_pay_link(url: str, tid: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Открыть банк и оплатить", url=url)],
        [InlineKeyboardButton(text="⬅️ Назад к оплате", callback_data=f"t_pay:{tid}")]
    ])



@router.callback_query(F.data.startswith("t_pay_player:"))
async def t_pay_player(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    # команда может быть None — платит как одиночка
    team_name = None
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT team FROM users WHERE user_id=?", (cb.from_user.id,))
        r = await cur.fetchone()
        team_name = r[0] if r and r[0] else None

    link = build_payment_link(PLAYER_FEE, tid, cb.from_user.id, team_name)
    msg = (f"Оплата за <b>игрока</b>: {PLAYER_FEE} ₽\n\n"
           "Нажми кнопку ниже — откроется приложение банка с суммой и комментарием.\n"
           "После оплаты вернись в бота и нажми «Оплатили?» (добавим позже автопроверку).")
    await cb.message.edit_text(msg, reply_markup=kb_pay_link(link, tid), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("t_pay:"))
async def t_pay(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])

    text = (
        "<b>Оплата взноса</b>\n\n"
        "🧑 За игрока — 500 ₽\n"
        "👥 За команду (до 3 игроков) — 1500 ₽\n"
        "👥 За команду (4 игрока и более) — 2000 ₽\n\n"
        "Нажми на кнопку ниже, чтобы открыть приложение банка и перевести нужную сумму.\n"
        "❗ В комментарии к переводу укажи название своей команды."
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Оплатить через СБП", url=PAY_LINK)],
        [InlineKeyboardButton(text="⬅️ Назад к турниру", callback_data=f"open_tournament:{tid}")]
    ])

    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await cb.answer()

def kb_admin_tournaments_list():
    tours = get_tournaments(active_only=False)
    rows = []
    for tid, name, status in tours:
        rows.append([InlineKeyboardButton(text=f"{name} · {status}", callback_data=f"admin_tournament:{tid}")])
    rows.append([InlineKeyboardButton(text="➕ Создать турнир", callback_data="admin_tournament_new")])
    rows.append([InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("t_pay_team:"))
async def t_pay_team(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    # определяем команду и её размер
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT team FROM users WHERE user_id=?", (cb.from_user.id,))
        r = await cur.fetchone()
        team_name = r[0] if r and r[0] else None
        if not team_name:
            await cb.answer("Сначала вступи в команду.", show_alert=True)
            await cb.message.edit_text("Ты не в команде.", reply_markup=kb_tournament_menu(tid, cb.from_user.id))
            return
        cur2 = await db.execute("SELECT COUNT(*) FROM teams WHERE team_name=?", (team_name,))
        (team_size,) = await cur2.fetchone()

    amount = TEAM_FEE_3 if team_size <= 3 else TEAM_FEE_4PLUS
    link = build_payment_link(amount, tid, cb.from_user.id, team_name)
    msg = (f"Оплата за <b>команду</b>: {amount} ₽ (игроков: {team_size})\n\n"
           "Нажми кнопку ниже — откроется приложение банка с суммой и комментарием.\n"
           "После оплаты вернись в бота и нажми «Оплатили?» (добавим позже автопроверку).")
    await cb.message.edit_text(msg, reply_markup=kb_pay_link(link, tid), parse_mode="HTML")
    await cb.answer()


# ---- USER STATE IN TOURNAMENT ----
async def get_user_state(user_id: int, tid: int):
    state = {
        "team_name": None,
        "in_team": False,
        "is_captain": False,
        "is_free_agent": False,
    }

    async with aiosqlite.connect(DB_PATH) as db:
        # 1) Текущая команда пользователя (глобально)
        cur = await db.execute("SELECT team FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        team_name = row[0] if row and row[0] else None
        state["team_name"] = team_name

        # 2) Состоит ли он в команде ЭТОГО турнира
        if team_name:
            # ВАРИАНТ А: если есть колонка tournament_id в teams
            try:
                cur = await db.execute(
                    "SELECT 1 FROM teams WHERE team_name=? AND tournament_id=? AND member_id=? LIMIT 1",
                    (team_name, tid, user_id)
                )
                state["in_team"] = (await cur.fetchone()) is not None
            except Exception:
                # ВАРИАНТ Б: если нет tournament_id — проверяем факт принадлежности к команде без привязки к tid
                cur = await db.execute(
                    "SELECT 1 FROM teams WHERE team_name=? AND member_id=? LIMIT 1",
                    (team_name, user_id)
                )
                state["in_team"] = (await cur.fetchone()) is not None

            # Капитан?
            cur = await db.execute(
                "SELECT 1 FROM team_captains WHERE team_name=? AND user_id=? LIMIT 1",
                (team_name, user_id)
            )
            state["is_captain"] = (await cur.fetchone()) is not None

        # 3) Является ли свободным игроком в этом турнире
        try:
            cur = await db.execute(
                "SELECT 1 FROM free_agents WHERE tournament_id=? AND user_id=? LIMIT 1",
                (tid, user_id)
            )
            state["is_free_agent"] = (await cur.fetchone()) is not None
        except Exception:
            # если таблицы нет — считаем, что не free-agent
            state["is_free_agent"] = False

    # Удобные производные
    


def kb_admin_ms_row(mid, tid, finished=False):
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✏️ Изменить счёт", callback_data=f"admin_ms_edit:{mid}:{tid}"),
        InlineKeyboardButton(text="🎮 LIVE", callback_data=f"match_live:{mid}")
    )
    if not finished:
        kb.row(InlineKeyboardButton(text="🏁 Завершить", callback_data=f"live_finish:{mid}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_ms:{tid}"))
    return kb.as_markup()

def kb_admin_ms_del_confirm(mid:int, tid:int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Подтвердить удаление", callback_data=f"admin_ms_del:{mid}:{tid}")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"admin_ms_list:{tid}")]
    ])

@router.callback_query(F.data.startswith("admin_tournament_archive:"))
async def admin_tournament_archive(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    tid = int(cb.data.split(":")[1])
    with db() as con:
        con.execute("UPDATE tournaments SET status='archived' WHERE id=?", (tid,))
        con.commit()
    await cb.message.edit_text(f"📦 Турнир ID {tid} перенесён в архив.")
    await cb.answer("Архивирован")


# ==== KEYBOARDS: Admin managers & User stats ====
def kb_admin_tt_menu(tid:int):
    rows = []
    for name in tt_list_names(tid):
        paid = tt_get_paid(tid, name)
        label = f"{'✅' if paid else '❌'} {name}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"admin_tt_team:{tid}:{name}")])
    rows += [
        [InlineKeyboardButton(text="➕ Добавить команду", callback_data=f"admin_tt_add:{tid}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_tournament:{tid}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_admin_tt_confirm_delete(tid:int, name:str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_tt_del:{tid}:{name}")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"admin_tt:{tid}")]
    ])

def kb_admin_ms_menu(tid:int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить матч", callback_data=f"admin_ms_add:{tid}")],
        [InlineKeyboardButton(text="✏️ Внести счёт", callback_data=f"admin_ms_score:{tid}")],
        [InlineKeyboardButton(text="🗒 Все матчи", callback_data=f"admin_ms_list:{tid}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_tournament:{tid}")]
    ])




@router.callback_query(F.data == "achievements_all")
async def achievements_all(cb: CallbackQuery):
    """
    Красивое меню ачивок по уровням (MarkdownV2 + экранирование),
    без конфликтов с default parse_mode=HTML.
    """
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 EASY",    callback_data="ach_tier:easy"),
         InlineKeyboardButton(text="⚡ MEDIUM",  callback_data="ach_tier:medium")],
        [InlineKeyboardButton(text="👑 HARD",    callback_data="ach_tier:hard"),
         InlineKeyboardButton(text="💎 ULTRA",   callback_data="ach_tier:ultra")],
        [InlineKeyboardButton(text="👕 ULTIMATE", callback_data="ach_tier:ultimate")],
         [InlineKeyboardButton(text="⬅️ К разделам", callback_data="ach_back")]
    ])

    head = "🏅 *Система ачивок VZALE*\n"
    body = (
        "Выбирай уровень, чтобы посмотреть достижения:\n\n"
        "🎯 *EASY* — для новичков\n"
        "⚡ *MEDIUM* — прояви себя\n"
        "👑 *HARD* — для постоянных\n"
        "💎 *ULTRA* — легендарные\n"
        "👕 *ULTIMATE GOAL* — мета-цель\n"
    )
    # экранируем только обычный текст, не трогая наши *...* для жирного
    text = head + esc_md2(body)

    try:
        await cb.message.edit_text(text, parse_mode="MarkdownV2", reply_markup=kb)
    except TelegramBadRequest as e:
        # просто тихо игнорируем попытку «неизменённого» сообщения
        if "message is not modified" not in str(e).lower():
            raise
    await cb.answer()

@router.callback_query(F.data.startswith("ach_tier:"))
async def achievements_tier(cb: CallbackQuery):
    """
    Рендер карточек выбранного уровня (MarkdownV2 + экранирование).
    """
    import aiosqlite
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    DB_PATH = "tournament.db"
    tier = cb.data.split(":", 1)[1]

    titles = {
        "easy":     "🎯 *EASY* — для новичков",
        "medium":   "⚡ *MEDIUM* — прояви себя",
        "hard":     "👑 *HARD* — для постоянных игроков",
        "ultra":    "💎 *ULTRA* — легендарные",
        "ultimate": "👕 *ULTIMATE GOAL*",
    }
    if tier not in titles:
        await cb.answer("Неизвестный раздел")
        return

    # навигация
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 EASY",    callback_data="ach_tier:easy"),
         InlineKeyboardButton(text="⚡ MEDIUM",  callback_data="ach_tier:medium")],
        [InlineKeyboardButton(text="👑 HARD",    callback_data="ach_tier:hard"),
         InlineKeyboardButton(text="💎 ULTRA",   callback_data="ach_tier:ultra")],
        [InlineKeyboardButton(text="👕 ULTIMATE", callback_data="ach_tier:ultimate")],
        [InlineKeyboardButton(text="⬅️ К разделам", callback_data="ach_back")],
    ])

    # данные
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT COALESCE(emoji,'•'), title, COALESCE(description,''), order_index
            FROM achievements
            WHERE tier=?
            ORDER BY order_index, title COLLATE NOCASE
        """, (tier,))
        rows = await cur.fetchall()

    lines = [titles[tier], ""]
    if not rows:
        lines.append(esc_md2("В этом разделе пока пусто"))
    else:
        for emoji, title, desc, _ in rows:
            # карточка: эмодзи + жирный тайтл + описание с новой строки
            t = esc_md2(title)
            d = esc_md2(desc)
            if d:
                lines.append(f"• {emoji} *{t}*\n  ▸ {d}")
            else:
                lines.append(f"• {emoji} *{t}*")
            lines.append("")  # отступ

    text = "\n".join(lines).strip()

    try:
        await cb.message.edit_text(text, parse_mode="MarkdownV2", reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
    await cb.answer()


import aiosqlite, re
DB_PATH = "tournament.db"

def esc_md(s: str) -> str:
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', s or "")

TITLES = {
    "easy":    "🎯 *EASY* — для новичков",
    "medium":  "⚡ *MEDIUM* — прояви себя",
    "hard":    "👑 *HARD* — для постоянных игроков",
    "ultra":   "💎 *ULTRA* — легендарные",
    "ultimate":"👕 *ULTIMATE GOAL*",
}

# ========= AUTO-ACH UTILS =========

async def _table_exists(db, table: str) -> bool:
    cur = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return await cur.fetchone() is not None

async def _column_exists(db, table: str, column: str) -> bool:
    cur = await db.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in await cur.fetchall()]
    return column in cols

async def _all_tournaments() -> list[tuple[int,str,str]]:
    """[(id, name, status)] — если таблица tournaments есть, иначе пусто"""
    async with aiosqlite.connect(DB_PATH) as db:
        if not await _table_exists(db, "tournaments"):
            return []
        cur = await db.execute("SELECT id, name, COALESCE(status,'') FROM tournaments")
        return await cur.fetchall()

async def _teams_in_tournament(tid: int) -> list[str]:
    """Список команд турнира из всех доступных источников: roster, matches, tournament_team_names."""
    async with aiosqlite.connect(DB_PATH) as db:
        names = set()

        # A) ростер (если есть)
        if await _table_exists(db, "tournament_roster"):
            cur = await db.execute(
                "SELECT DISTINCT team_name FROM tournament_roster WHERE tournament_id=?",
                (tid,)
            )
            names |= {r[0] for r in await cur.fetchall()}

        # B) матчи (если есть)
        if await _table_exists(db, "matches_simple"):
            cur = await db.execute("""
                SELECT DISTINCT team_home_name FROM matches_simple WHERE tournament_id=?
                UNION
                SELECT DISTINCT team_away_name FROM matches_simple WHERE tournament_id=?
            """, (tid, tid))
            names |= {r[0] for r in await cur.fetchall()}

        # C) имена команд из админки турнира
        if await _table_exists(db, "tournament_team_names"):
            cur = await db.execute(
                "SELECT name FROM tournament_team_names WHERE tournament_id=?",
                (tid,)
            )
            names |= {r[0] for r in await cur.fetchall()}

        return sorted(n for n in names if n)


async def _roster_uids(tid: int, team: str) -> list[int]:
    """Игроки команды в турнире. Если roster пуст — берём из teams, потом из users."""
    async with aiosqlite.connect(DB_PATH) as db:
        uids: list[int] = []
        # 1) нормальный путь — tournament_roster
        if await _table_exists(db, "tournament_roster"):
            cur = await db.execute("""
                SELECT user_id FROM tournament_roster
                WHERE tournament_id=? AND team_name=?
            """, (tid, team))
            uids = [r[0] for r in await cur.fetchall()]
        if uids:
            return uids
        # 2) fallback — глобальная таблица teams (исторические данные)
        if await _table_exists(db, "teams") and await _column_exists(db, "teams", "member_id"):
            cur = await db.execute("SELECT DISTINCT member_id FROM teams WHERE team_name=?", (team,))
            uids = [r[0] for r in await cur.fetchall() if r[0]]
        if uids:
            return uids
        # 3) последний fallback — users.team == team
        if await _table_exists(db, "users") and await _column_exists(db, "users", "team"):
            cur = await db.execute("SELECT user_id FROM users WHERE team=?", (team,))
            uids = [r[0] for r in await cur.fetchall() if r[0]]
        return uids


async def _team_finished_games(tid: int, team: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        if not await _table_exists(db, "matches_simple"):
            return 0
        cur = await db.execute("""
            SELECT COUNT(*) FROM matches_simple
            WHERE tournament_id=? AND status='finished' AND (team_home_name=? OR team_away_name=?)
        """, (tid, team, team))
        (cnt,) = await cur.fetchone()
        return int(cnt or 0)

async def _team_win_count(tid: int, team: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        if not await _table_exists(db, "matches_simple"):
            return 0
        cur = await db.execute("""
            SELECT SUM(
                CASE
                  WHEN team_home_name=? AND score_home>score_away THEN 1
                  WHEN team_away_name=? AND score_away>score_home THEN 1
                  ELSE 0
                END
            )
            FROM matches_simple
            WHERE tournament_id=? AND status='finished'
        """, (team, team, tid))
        (wins,) = await cur.fetchone()
        return int(wins or 0)

async def _team_points_scored(tid: int, team: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        if not await _table_exists(db, "matches_simple"):
            return 0
        cur = await db.execute("""
            SELECT COALESCE(SUM(
              CASE
                WHEN team_home_name=? THEN score_home
                WHEN team_away_name=? THEN score_away
                ELSE 0
              END
            ),0)
            FROM matches_simple
            WHERE tournament_id=? AND status='finished'
        """, (team, team, tid))
        (pts,) = await cur.fetchone()
        return int(pts or 0)

async def _team_any_blowout(tid: int, team: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        if not await _table_exists(db, "matches_simple"):
            return False
        cur = await db.execute("""
            SELECT 1
            FROM matches_simple
            WHERE tournament_id=? AND status='finished'
              AND (
                 (team_home_name=? AND score_home - score_away >= 10) OR
                 (team_away_name=? AND score_away - score_home >= 10)
              )
            LIMIT 1
        """, (tid, team, team))
        return await cur.fetchone() is not None

async def _team_any_iron_defense_win(tid: int, team: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        if not await _table_exists(db, "matches_simple"):
            return False
        cur = await db.execute("""
            SELECT 1
            FROM matches_simple
            WHERE tournament_id=? AND status='finished'
              AND (
                (team_home_name=? AND score_home>score_away AND score_away<10)
                OR
                (team_away_name=? AND score_away>score_home AND score_home<10)
              )
            LIMIT 1
        """, (tid, team, team))
        return await cur.fetchone() is not None

async def _tournament_archived(tid: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        if not await _table_exists(db, "tournaments"):
            return False
        cur = await db.execute("SELECT COALESCE(status,'') FROM tournaments WHERE id=?", (tid,))
        row = await cur.fetchone()
        status = (row[0] if row else "").lower()
        return status in ("archived","finished","closed","done")

async def _uids_paid_in_team(tid: int, team: str) -> list[int]:
    """
    Возвращаем user_id тех, кто считается оплаченным.
    Поддерживаем:
      - флаг команды в tournament_team_names.paid
      - персональные player_payments.paid
    """
    uids = set()
    async with aiosqlite.connect(DB_PATH) as db:
        # A) персональные оплаты (если таблица есть)
        if await _table_exists(db, "player_payments") and await _column_exists(db, "player_payments", "paid"):
            cur = await db.execute("""
                SELECT pp.user_id
                FROM player_payments pp
                JOIN users u ON u.user_id=pp.user_id
                WHERE pp.tournament_id=? AND pp.paid=1 AND u.team=?
            """, (tid, team))
            uids |= {r[0] for r in await cur.fetchall()}

        # B) командная оплата через tournament_team_names.paid
        if await _table_exists(db, "tournament_team_names") and await _column_exists(db, "tournament_team_names", "paid"):
            cur = await db.execute("""
                SELECT paid FROM tournament_team_names WHERE tournament_id=? AND name=? LIMIT 1
            """, (tid, team))
            row = await cur.fetchone()
            team_paid = (row and row[0] == 1)
            if team_paid:
                # Все из ростера считаются оплаченными
                for uid in await _roster_uids(tid, team):
                    uids.add(uid)
    return list(uids)


# ========= AUTO-ACH BACKFILL =========

async def backfill_auto_achievements(tid: int | None = None) -> dict:
    """
    Анализирует текущие данные и автоматически проставляет ачивки игрокам (в рамках турниров).
    Возвращает словарь с количеством выданных штук по кодам.
    Что покрываем сейчас (без ручных судейских и без персональной детализации):
      EASY:   FIRST_MATCH, TEAM_CREATED*, PAID, FIRST_TOUR_FINISH
      MEDIUM: FIRST_WIN, WIN_STREAK3, HUNDRED_POINTS, IRON_DEFENSE, TEN_GAMES, BLOWOUT_WIN
      HARD:   CHAMPION*, TOP3*, (серийные можно добить позже)
      ULTRA:  UNDEFEATED_TOUR*, DYNASTY* (на финале/истории — TODO)
    Пометка * — зависит от твоей схемы результатов/капитанов и может быть пропущена, если нет данных.
    """
    awarded: dict[str,int] = {}
    # вспомогалка для инкремента
    def inc(code: str, n: int = 1):
        awarded[code] = awarded.get(code, 0) + n

    # какие турниры обрабатываем
    tids: list[int]
    if tid is None:
        tids = [t[0] for t in await _all_tournaments()] or []
    else:
        tids = [int(tid)]

    # если турнирной таблицы нет — попробуем хотя бы взять tid’ы из matches_simple
    if not tids:
        async with aiosqlite.connect(DB_PATH) as db:
            if await _table_exists(db, "matches_simple"):
                cur = await db.execute("SELECT DISTINCT tournament_id FROM matches_simple")
                tids = [r[0] for r in await cur.fetchall()]

    for TID in tids:
        teams = await _teams_in_tournament(TID)
        if not teams:
            continue

        # --- FIRST_TOUR_FINISH: всем из ростера, если турнир закрыт ---
     # --- FIRST_TOUR_FINISH: всем из команд турнира, если он закрыт ---
        if await _tournament_archived(TID):
            for team in teams:
                for uid in await _roster_uids(TID, team):
                    if await award_player_achievement(TID, uid, "FIRST_TOUR_FINISH"):
                        inc("FIRST_TOUR_FINISH")


        for team in teams:
            uids = await _roster_uids(TID, team)
            if not uids:
                continue

            games = await _team_finished_games(TID, team)
            wins  = await _team_win_count(TID, team)
            pts   = await _team_points_scored(TID, team)
            has_blowout = await _team_any_blowout(TID, team)
            has_iron    = await _team_any_iron_defense_win(TID, team)

            # сразу в начале цикла по team (после получения uids):
            if uids:
                for uid in uids:
                    if await award_player_achievement(TID, uid, "TEAM_CREATED"):
                        inc("TEAM_CREATED")


            # --- FIRST_MATCH: у команды есть хотя бы 1 завершённый матч ---
            if games >= 1:
                for uid in uids:
                    if await award_player_achievement(TID, uid, "FIRST_MATCH"):
                        inc("FIRST_MATCH")

            # --- FIRST_WIN: у команды есть хотя бы 1 победа ---
            if wins >= 1:
                for uid in uids:
                    if await award_player_achievement(TID, uid, "FIRST_WIN"):
                        inc("FIRST_WIN")

            # --- TEN_GAMES: сыграно >=10 матчей ---
            if games >= 10:
                for uid in uids:
                    if await award_player_achievement(TID, uid, "TEN_GAMES"):
                        inc("TEN_GAMES")

            # --- HUNDRED_POINTS: суммарно набрали >=100 ---
            if pts >= 100:
                for uid in uids:
                    if await award_player_achievement(TID, uid, "HUNDRED_POINTS"):
                        inc("HUNDRED_POINTS")

            # --- BLOWOUT_WIN: победа с разницей >=10 ---
            if has_blowout:
                for uid in uids:
                    if await award_player_achievement(TID, uid, "WIN_BY_10"):
                        inc("WIN_BY_10")

            # --- IRON_DEFENSE: победа, пропустили <10 ---
            if has_iron:
                for uid in uids:
                    if await award_player_achievement(TID, uid, "IRON_DEFENSE"):
                        inc("IRON_DEFENSE")

            # --- PAID: если есть отметка оплаты (персональная/командная) ---
            paid_uids = await _uids_paid_in_team(TID, team)
            for uid in paid_uids:
                if await award_player_achievement(TID, uid, "PAID"):
                    inc("PAID")

        # TODO (при наличии данных результатов):
        # - CHAMPION / TOP3 → раздать по итогам турнирной таблицы
        # - UNDEFEATED_TOUR (команда без поражений) → если wins==games>0
        # - DYNASTY (3 подряд) / LEGEND / и т.п. → по истории турниров

    return awarded



async def build_tier_text(tier: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT COALESCE(emoji,'•'), title, COALESCE(description,''), order_index
            FROM achievements
            WHERE tier=?
            ORDER BY order_index, title COLLATE NOCASE
        """, (tier,))
        rows = await cur.fetchall()

    if not rows:
        return TITLES[tier] + "\n\n_В этом разделе пока пусто_"

    lines = [TITLES[tier], ""]
    # «карточки»: эмодзи-пуля + жирный заголовок + серенькое описание
    for e, title, desc, _ in rows:
        t = esc_md(title)
        d = esc_md(desc)
        if d:
            lines.append(f"• {e} *{t}*\n  ▸ {d}")
        else:
            lines.append(f"• {e} *{t}*")
        lines.append("")  # отступ между карточками

    return "\n".join(lines).strip()



def kb_pick_team(tid:int, exclude:str|None=None):
    names = [n for n in tt_list_names(tid) if n != (exclude or "")]
    rows, row = [], []
    for name in names:
        row.append(InlineKeyboardButton(text=name, callback_data=f"admin_ms_pick:{tid}:{name}"))
        if len(row)==2:
            rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin_ms:{tid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_ms_confirm_short(tid:int, home:str, away:str, stage:str|None):
    s = stage or "без этапа"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Сохранить ({home} — {away}, {s})", callback_data=f"admin_ms_ok:{tid}")],
        [InlineKeyboardButton(text="↩️ Изменить", callback_data=f"admin_ms_add:{tid}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin_ms:{tid}")]
    ])


@router.callback_query(F.data.startswith("ach_tier:"))
async def achievements_tier(cb: CallbackQuery):
    tier = cb.data.split(":", 1)[1]
    if tier not in TITLES:
        await cb.answer("Неизвестный раздел", show_alert=False)
        return
    text = await build_tier_text(tier)
    try:
        await cb.message.edit_text(text, parse_mode="MarkdownV2", reply_markup=kb_tier_nav(tier))
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
    await cb.answer()

@router.callback_query(F.data == "ach_back")
async def ach_back(cb: CallbackQuery):
    await cb.message.edit_text(
        f"Главное меню\nТекущий турнир: {get_current_tournament_name(cb.from_user.id)}",
        reply_markup=kb_global(cb.from_user.id)
    )
    await cb.answer()


def kb_user_stats_menu(tid:int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Таблица", callback_data=f"t_stats:{tid}")],
        [InlineKeyboardButton(text="📅 Последние матчи", callback_data=f"t_last:{tid}")],
        [InlineKeyboardButton(text="📅 Ближайшие матчи", callback_data=f"t_upc:{tid}")],
        [InlineKeyboardButton(text="🔎 Матчи по команде", callback_data=f"t_pickteam:{tid}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"open_tournament:{tid}")]
    ])


@router.callback_query(F.data.startswith("t_pickteam:"))
async def t_pickteam(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    await cb.message.edit_text("Выбери команду:", reply_markup=kb_pick_team_public(tid)); await cb.answer()

@router.callback_query(F.data.startswith("t_team:"))
async def t_team_matches(cb: CallbackQuery):
    _, tid, name = cb.data.split(":")
    tid = int(tid)
    with db() as con:
        rows = con.execute("""
            SELECT team_home_name, score_home, score_away, team_away_name, stage, status
            FROM matches_simple
            WHERE tournament_id=? AND (team_home_name=? OR team_away_name=?)
            ORDER BY id DESC LIMIT 15
        """, (tid, name, name)).fetchall()
    if not rows:
        await cb.message.edit_text(f"Матчей команды «{name}» пока нет.", reply_markup=kb_user_stats_menu(tid)); await cb.answer(); return
    lines = [f"Матчи «{name}»:\n"]
    for h,sh,sa,a,stage,st in rows:
        if st=='finished':
            line = f"{h} {sh} — {sa} {a}"
        else:
            line = f"{h} — {a} (ожидает счёта)"
        if stage: line += f" ({stage})"
        lines.append(line)
    await cb.message.edit_text("\n".join(lines), reply_markup=kb_user_stats_menu(tid)); await cb.answer()

@router.callback_query(F.data.startswith("admin_pay_team:"))
async def admin_pay_team(cb: CallbackQuery):
    _, tid, name = cb.data.split(":",2)
    tid = int(tid)
    new_val = team_toggle_paid(tid, name)
    status = "✅ Оплачено" if new_val==1 else "❌ Не оплачено"
    await cb.answer(f"Статус: {status}")

@router.callback_query(F.data.startswith("admin_pay_player:"))
async def admin_pay_player(cb: CallbackQuery):
    _, tid, uid = cb.data.split(":")
    tid, uid = int(tid), int(uid)
    new_val = player_toggle_paid(uid, tid)
    status = "✅ Оплачено" if new_val==1 else "❌ Не оплачено"
    await cb.answer(f"Статус игрока: {status}")


from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def kb_achievements_menu() -> InlineKeyboardMarkup:
    # экран с выбором разделов
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 EASY",   callback_data="ach_tier:easy"),
         InlineKeyboardButton(text="⚡ MEDIUM", callback_data="ach_tier:medium")],
        [InlineKeyboardButton(text="👑 HARD",   callback_data="ach_tier:hard"),
         InlineKeyboardButton(text="💎 ULTRA",  callback_data="ach_tier:ultra")],
        [InlineKeyboardButton(text="👕 ULTIMATE", callback_data="ach_tier:ultimate")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_global")]   # ← КНОПКА ДОМОЙ
    ])

def kb_tier_nav() -> InlineKeyboardMarkup:
    # навигация внутри раздела
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 EASY",   callback_data="ach_tier:easy"),
         InlineKeyboardButton(text="⚡ MEDIUM", callback_data="ach_tier:medium")],
        [InlineKeyboardButton(text="👑 HARD",   callback_data="ach_tier:hard"),
         InlineKeyboardButton(text="💎 ULTRA",  callback_data="ach_tier:ultra")],
        [InlineKeyboardButton(text="👕 ULTIMATE", callback_data="ach_tier:ultimate")],
        [InlineKeyboardButton(text="⬅️ К разделам", callback_data="ach_sections")]      # ← ВОЗВРАТ К СПИСКУ
    ])



async def get_main_menu(user_id):
    kb = InlineKeyboardBuilder()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT team FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        in_team = row and row[0]
        cursor = await db.execute("SELECT 1 FROM free_agents WHERE user_id = ?", (user_id,))
        is_free_agent = await cursor.fetchone() is not None

    if in_team:
        kb.row(InlineKeyboardButton(text="🏀 Моя команда", callback_data="my_team"))
        kb.row(InlineKeyboardButton(text="💡 Предложить идею/ошибку", callback_data="suggest_feature"))
        kb.row(InlineKeyboardButton(text="🔐 Код приглашения", callback_data=f"show_invite:{in_team}")) 
        kb.row(InlineKeyboardButton(text="🚪 Выйти из команды", callback_data="leave_team"))
        kb.row(InlineKeyboardButton(text="📋 Список команд", callback_data="list_teams"))

    else:
        kb.row(InlineKeyboardButton(text="🔄 Присоединиться к команде", callback_data="rejoin_team"))
        kb.row(InlineKeyboardButton(text="💡 Предложить идею/ошибку", callback_data="suggest_feature"))


    if is_free_agent:
        kb.row(InlineKeyboardButton(text="🚫 Удалить анкету свободного игрока", callback_data="leave_free_agents"))
        kb.row(InlineKeyboardButton(text="💡 Предложить идею/ошибку", callback_data="suggest_feature"))


    if user_id in ADMINS:
        kb.row(InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_panel"))
        kb.row(InlineKeyboardButton(text="🧍 Свободные игроки", callback_data="free_agents"))
        kb.row(InlineKeyboardButton(text="📋 Список команд", callback_data="list_teams"))

    kb.row(InlineKeyboardButton(text="🗑 Удалить профиль", callback_data="delete_profile"))
    return kb.as_markup()



def get_current_tournament_name(user_id: int) -> str:
    tid = get_user_current_tournament(user_id)
    t = get_tournament_by_id(tid) if tid else None
    return t[1] if t else "не выбран"


@router.callback_query(F.data.startswith("t_upc:"))
async def t_upcoming(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    rows = ms_upcoming(tid, n=10)
    if not rows:
        await cb.message.edit_text("Предстоящих матчей пока нет.", reply_markup=kb_user_stats_menu(tid)); await cb.answer(); return
    lines = ["📅 Ближайшие матчи\n"]
    for h,a,stage in rows:
        s = f" ({stage})" if stage else ""
        lines.append(f"{h} — {a}{s}")
    await cb.message.edit_text("\n".join(lines), reply_markup=kb_user_stats_menu(tid)); await cb.answer()



@router.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext):
    user_id = message.from_user.id

    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        payload = args[1]

        # 1) веб-логин: /start web_<token>
        if payload.startswith("web_"):
            token = payload.split("_", 1)[1]
            try:
                async with aiohttp.ClientSession() as session:
                    resp = await session.post(
                        f"{WEB_AUTH_BASE}/api/auth/qr/confirm",
                        json={"token": token, "telegramId": user_id},
                        timeout=5,
                    )
                if resp.status == 200:
                    await message.answer(
                        "✅ Вход на сайте подтверждён!\n"
                        "Можно вернуться в браузер, страница сама увидит это."
                    )
                else:
                    await message.answer(
                        "⚠️ Не удалось подтвердить вход на сайте.\n"
                        "Токен мог устареть, попробуй заново открыть страницу входа."
                    )
            except Exception:
                await message.answer(
                    "⚠️ Сейчас не удалось связаться с сайтом.\n"
                    "Попробуй повторить вход немного позже."
                )

        # 2) deep-link для турниров: /start tid_<id>
        elif payload.startswith("tid_"):
            try:
                tid = int(payload.split("_", 1)[1])
                set_user_current_tournament(user_id, tid)
            except Exception:
                pass

    # дальше — твоя логика проверки user_exists и онбординг
    try:
        exists = await user_exists(user_id)
    except:
        exists = False

    if exists:
        title = f"Главное меню\nТекущий турнир: {get_current_tournament_name(user_id)}"
        await message.answer(title, reply_markup=kb_global(user_id))
        return

    await message.answer(
        "👋 Привет! Это VZALE — уличные турниры 3×3.\n\n"
        "Чтобы участвовать, нужна регистрация.\n"
        "✍️ Напиши, пожалуйста, свои ФИО одним сообщением:"
    )
    await state.set_state(Form.waiting_for_name)

def kb_admin_tournament_manage(tid:int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Переименовать",            callback_data=f"admin_tournament_rename:{tid}")],
        [InlineKeyboardButton(text="📅 Дата/место",                callback_data=f"admin_tournament_whenwhere:{tid}")],
        [InlineKeyboardButton(text="🚪 Открыть регистрацию",       callback_data=f"admin_tournament_open:{tid}")],
        [InlineKeyboardButton(text="🔒 Закрыть регистрацию",       callback_data=f"admin_tournament_close:{tid}")],
        [InlineKeyboardButton(text="ℹ️ Редактировать разделы Info",callback_data=f"admin_tinfo:{tid}")],
        [InlineKeyboardButton(text="👥 Команды турнира",           callback_data=f"admin_tt:{tid}")],
        [InlineKeyboardButton(text="📊 Матчи / Счёт",              callback_data=f"admin_ms:{tid}")],
        [InlineKeyboardButton(text="👁 Открыть как пользователь",  callback_data=f"open_tournament:{tid}")],
        [InlineKeyboardButton(text="🔗 Скопировать deep-link",     callback_data=f"admin_tournament_link:{tid}")],
        [InlineKeyboardButton(text="📦 Архивировать турнир",       callback_data=f"admin_tournament_archive:{tid}")],
        [InlineKeyboardButton(text="⬅️ К списку турниров",         callback_data="admin_tournaments")],
    ])

def kb_global_for_user(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🏆 Турниры", callback_data="tournaments")],
        [InlineKeyboardButton(text="ℹ️ Информация", callback_data="info")],
    ]
    # показываем пункт «Админ-панель» только админам
    if user_id in ADMINS:
        rows.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_tournaments")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

"""
# Хендлер старта с поддержкой deep-link /start tid_2
@router.message(CommandStart())
async def start_cmd(message: Message, state):
    user_id = message.from_user.id

    # deep-link: /start tid_2 → сохраняем выбранный турнир
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("tid_"):
        try:
            tid = int(args[1].split("_", 1)[1])
            set_user_current_tournament(user_id, tid)
        except Exception:
            pass

    # если пользователь уже есть в БД → показать ГЛОБАЛЬНОЕ меню
    try:
        exists = await user_exists(user_id)  # у тебя эта функция уже есть
    except:
        # если у тебя нет user_exists как async — замени на свой способ проверки
        exists = True

    if exists:
        await message.answer("Главное меню:", reply_markup=kb_global(user_id))
        return

    # иначе — онбординг как у тебя было раньше (ФИО и т.д.)
    await message.answer(
        "👋 Привет! Это VZALE — уличные турниры 3×3.\n\n"
        "Чтобы участвовать, нужна регистрация.\n"
        "✍️ Напиши, пожалуйста, свои ФИО одним сообщением:"
    )
    # дальше остаётся твоя логика FSM для нового пользователя

"""
"""
@router.message(F.text == "/start")
async def start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if await user_exists(user_id):
        menu = await get_main_menu(user_id)
        await message.answer("✅ Ты уже зарегистрирован!\nВыбери действие:", reply_markup=menu)
        return

    # Обновлённый привет/онбординг
    await message.answer(
        "👋 Привет! Это VZALE — уличные турниры 3×3.\n\n"
        "Чтобы участвовать, нужна регистрация.\n"
        "✍️ Напиши, пожалуйста, свои ФИО одним сообщением:"
    )
    await state.set_state(Form.waiting_for_name)
"""
@router.message(Form.waiting_for_name)
async def enter_name(message: Message, state: FSMContext):
    # 1) нормализуем имя
    full_name = " ".join(message.text.split())
    if len(full_name) < 2 or len(full_name) > 60:
        await message.reply("Имя выглядит странно 🤔 Попробуй покороче и без лишних символов.")
        return

    # 2) сохраняем в FSM (если нужно где-то ещё) и в БД
    await state.update_data(full_name=full_name)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, full_name)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET full_name = excluded.full_name
            """,
            (message.from_user.id, full_name)
        )
        await db.commit()

    # 3) показываем главное меню и выходим из машины состояний
    await message.answer("Отлично! Переходим в главное меню 👇", reply_markup=kb_global(message.from_user.id))
    await state.clear()

# === ВЫХОД ИЗ КОМАНДЫ (в контексте турнира) ===

@router.callback_query(F.data.startswith("t_leave:"))
async def t_leave(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])

    # проверим, что пользователь вообще в команде
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT team FROM users WHERE user_id=?", (cb.from_user.id,))
        row = await cur.fetchone()
    team = row[0] if row and row[0] else None

    if not team:
        await cb.answer("Ты не в команде.", show_alert=True)
        await cb.message.edit_text(
            f"Меню «{get_tournament_by_id(tid)[1]}»",
            reply_markup=kb_tournament_menu(tid, cb.from_user.id)
        )
        return

    # спросим подтверждение
    await cb.message.edit_text(
        f"🚪 Выйти из команды <b>{team}</b>?\n\nПосле выхода ты сможешь присоединиться к другой или создать свою.",
        reply_markup=kb_leave_confirm(tid)
    )
    await cb.answer()







@router.callback_query(F.data.startswith("t_leave_yes:"))
async def t_leave_yes(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    uid = cb.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET team=NULL WHERE user_id=?", (uid,))
        await db.execute("DELETE FROM teams WHERE member_id=?", (uid,))
        await db.commit()

    await cb.message.edit_text(
        "✅ Ты вышел из команды.",
        reply_markup=kb_tournament_menu(tid, uid)
    )
    await cb.answer("Готово")

def kb_leave_confirm(tid: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, выйти", callback_data=f"t_leave_yes:{tid}")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"tournament:{tid}")]
    ])


@router.callback_query(F.data == "back_global")
async def back_global(cb: CallbackQuery):
    title = f"Главное меню\nТекущий турнир: {get_current_tournament_name(cb.from_user.id)}"
    await cb.message.edit_text(title, reply_markup=kb_global(cb.from_user.id))
    await cb.answer()

# --- PAYMENT CONFIG ---
PLAYER_FEE = 500
TEAM_FEE_3 = 1500
TEAM_FEE_4PLUS = 2000

# Шаблон ссылки на оплату. ОБЯЗАТЕЛЬНО поменяй на реальный deeplink твоего банка/СБП.
# Вставь {amount} где должна подставляться сумма и {comment} для комментария платежа.
# Примеры для разных банков см. в README/комменте проекта; здесь оставляем универсальный шаблон.
PAYMENT_LINK_TEMPLATE = "https://example.bank/pay?amount={amount}&comment={comment}"

def build_payment_link(amount: int, tid: int, user_id: int, team_name: str | None) -> str:
    comment = f"VZALE_T{tid}" + (f"_{team_name}" if team_name else f"_U{user_id}")
    return PAYMENT_LINK_TEMPLATE.format(amount=amount, comment=comment)


@router.callback_query(F.data == "admin_tournaments")
async def admin_tournaments(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    await cb.message.edit_text("🏆 Турниры:", reply_markup=kb_admin_tournaments_list())
    await cb.answer()

@router.callback_query(F.data == "admin_tournament_new")
async def admin_tournament_new(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    await cb.message.edit_text("Название нового турнира?")
    await state.set_state(AdminForm.waiting_tournament_name)  # ← сюда
    await cb.answer()

@router.message(AdminForm.waiting_tournament_name)
async def admin_tournament_name_input(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("Введите название."); return
    with db() as con:
        con.execute("INSERT INTO tournaments(name, status) VALUES(?, ?)", (name, "draft"))
        con.commit()
        tid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    await state.clear()
    await message.answer(
        f"Создан: {name}\nID: {tid}",
        reply_markup=kb_admin_tournament_manage(tid)
    )




# === ADMIN: Команды турнира ===
@router.callback_query(F.data.startswith("admin_tt:"))
async def admin_tt_menu_open(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    tid = int(cb.data.split(":")[1])
    await cb.message.edit_text("👥 Команды турнира:", reply_markup=kb_admin_tt_menu(tid))
    await cb.answer()

@router.callback_query(F.data.startswith("admin_tt_add:"))
async def admin_tt_add_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    tid = int(cb.data.split(":")[1])
    await state.update_data(_tt_tid=tid)
    await cb.message.edit_text("Введи название команды одним сообщением:")
    await state.set_state(AdminTT.waiting_team_name)
    await cb.answer()

@router.message(AdminTT.waiting_team_name)
async def admin_tt_add_name_input(message: Message, state: FSMContext):
    data = await state.get_data()
    tid = data.get("_tt_tid")
    name = (message.text or "").strip()
    if not tid:
        await state.clear()
        await message.answer("Сессия потеряна. Открой заново через админку.")
        return
    ok = tt_add_name(tid, name)
    await state.clear()
    await message.answer("✅ Добавлено." if ok else "⚠️ Такая команда уже есть или имя пустое.",
                         reply_markup=kb_admin_tt_menu(tid))

@router.callback_query(F.data.startswith("admin_tt_delask:"))
async def admin_tt_del_ask(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    _, tid, name = cb.data.split(":")
    tid = int(tid)
    await cb.message.edit_text(f"Удалить команду «{name}»?",
                               reply_markup=kb_admin_tt_confirm_delete(tid, name))
    await cb.answer()

@router.callback_query(F.data.startswith("admin_tt_del:"))
async def admin_tt_del(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    _, tid, name = cb.data.split(":")
    tid = int(tid)
    cnt = tt_delete_name(tid, name)
    await cb.message.edit_text(("✅ Удалено." if cnt else "⚠️ Не найдено."),
                               reply_markup=kb_admin_tt_menu(tid))
    await cb.answer()

@router.callback_query(F.data.startswith("admin_tt_team:"))
async def admin_tt_team_menu(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    _, tid, team_name = cb.data.split(":", 2)
    tid = int(tid)

    # список игроков команды + их статус оплаты по этому турниру
    with db() as con:
        players = con.execute("""
            SELECT t.member_id, t.member_name, COALESCE(pp.paid,0) AS paid
            FROM teams t
            LEFT JOIN player_payments pp
              ON pp.user_id = t.member_id AND pp.tournament_id = ?
            WHERE t.team_name = ?
            ORDER BY t.member_name COLLATE NOCASE
        """, (tid, team_name)).fetchall()

    txt = f"Команда: <b>{team_name}</b>\n"
    txt += f"Статус команды: {'✅ оплачено' if team_get_paid(tid, team_name) else '❌ не оплачено'}\n\n"
    if players:
        txt += "Игроки:\n" + "\n".join(f"• {'✅' if p[2] else '❌'} {p[1]} (id:{p[0]})" for p in players)
    else:
        txt += "Игроки: список пуст"

    await cb.message.edit_text(txt, reply_markup=kb_admin_team_payment(tid, team_name, players))
    await cb.answer()


@router.callback_query(F.data.startswith("admin_tournament_open:"))
async def admin_tournament_open(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    tid = int(cb.data.split(":")[1])
    with db() as con:
        con.execute("UPDATE tournaments SET status='registration_open' WHERE id=?", (tid,))
        con.commit()
    await admin_tournament_open_card(cb)

@router.callback_query(F.data.startswith("admin_tournament:"))
async def admin_tournament_open_card(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    tid = int(cb.data.split(":")[1])
    t = get_tournament_by_id(tid)
    if not t:
        await cb.answer("Турнир не найден", show_alert=True); return
    name, status = t[1], t[2]
    await cb.message.edit_text(f"🏆 {name}\nСтатус: {status}",
                               reply_markup=kb_admin_tournament_manage(tid))
    await cb.answer()


@router.callback_query(F.data.startswith("admin_tournament_close:"))
async def admin_tournament_close(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    tid = int(cb.data.split(":")[1])
    with db() as con:
        con.execute("UPDATE tournaments SET status='closed' WHERE id=?", (tid,))
        con.commit()
    await admin_tournament_open_card(cb)

@router.callback_query(F.data.startswith("admin_tournament_link:"))
async def admin_tournament_link(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    tid = int(cb.data.split(":")[1])
    # deep-link: /start tid_<id>
    await cb.answer("Скопировано в буфер обмена нельзя через бота — просто отправлю текстом ниже.")
    await cb.message.answer(f"Deep-link: <code>/start tid_{tid}</code>")


# === ADMIN: Матчи / Счёт ===
@router.callback_query(F.data.startswith("admin_ms:"))
async def admin_ms_menu_open(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    tid = int(cb.data.split(":")[1])
    await cb.message.edit_text("📊 Матчи / Счёт:", reply_markup=kb_admin_ms_menu(tid))
    await cb.answer()

@router.callback_query(F.data.startswith("admin_ms_add:"))
async def admin_ms_add_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    tid = int(cb.data.split(":")[1])
    await state.update_data(_ms_tid=tid, _ms_home=None, _ms_away=None, _ms_stage=None)
    await cb.message.edit_text("Выбери Команду A:", reply_markup=kb_pick_team(tid))
    await cb.answer()
    await state.set_state(AdminMatches.add_pick_home)

@router.callback_query(AdminMatches.add_pick_home, F.data.startswith("admin_ms_pick:"))
async def admin_ms_pick_home(cb: CallbackQuery, state: FSMContext):
    _, tid, name = cb.data.split(":")
    tid = int(tid)
    await state.update_data(_ms_home=name)
    await cb.message.edit_text(f"Команда A: {name}\n\nВыбери Команду B:",
                               reply_markup=kb_pick_team(tid, exclude=name))
    await cb.answer()
    await state.set_state(AdminMatches.add_pick_away)

@router.callback_query(AdminMatches.add_pick_away, F.data.startswith("admin_ms_pick:"))
async def admin_ms_pick_away(cb: CallbackQuery, state: FSMContext):
    _, tid, name = cb.data.split(":")
    tid = int(tid)
    data = await state.get_data()
    home = data.get("_ms_home")
    if name == home:
        await cb.answer("Нельзя выбрать ту же команду", show_alert=True); return
    await state.update_data(_ms_away=name)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Группы", callback_data="admin_ms_stage:Группы"),
         InlineKeyboardButton(text="Плей-офф", callback_data="admin_ms_stage:Плей-офф")],
        [InlineKeyboardButton(text="Пропустить", callback_data="admin_ms_stage:")]
    ])
    await cb.message.edit_text(f"Команда A: {home}\nКоманда B: {name}\n\nВыбери этап (или пропусти):", reply_markup=kb)
    await cb.answer()
    await state.set_state(AdminMatches.add_pick_stage)

@router.callback_query(AdminMatches.add_pick_stage, F.data.startswith("admin_ms_stage:"))
async def admin_ms_pick_stage(cb: CallbackQuery, state: FSMContext):
    stage = cb.data.split(":",1)[1]
    data = await state.get_data()
    tid, home, away = data["_ms_tid"], data["_ms_home"], data["_ms_away"]
    await state.update_data(_ms_stage=(stage or None))
    await cb.message.edit_text(
        "Подтвердите матч:",
        reply_markup=kb_ms_confirm_short(tid, home, away, stage or None)
    )
    await cb.answer()


@router.callback_query(F.data.startswith("admin_ms_ok:"))
async def admin_ms_ok(cb: CallbackQuery, state: FSMContext):
    tid = int(cb.data.split(":")[1])
    data = await state.get_data()
    home, away, stage = data.get("_ms_home"), data.get("_ms_away"), data.get("_ms_stage")
    if not (home and away):
        await cb.answer("Сессия потеряна. Создайте матч заново.", show_alert=True); return
    ms_add_match(tid, home, away, stage)
    await state.clear()
    await cb.message.edit_text("✅ Матч создан.", reply_markup=kb_admin_ms_menu(tid))
    await cb.answer()


@router.callback_query(F.data.startswith("admin_ms_score:"))
async def admin_ms_score_menu(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    tid = int(cb.data.split(":")[1])
    open_matches = ms_list_matches(tid, only_open=True, limit=25)
    if not open_matches:
        await cb.message.edit_text("Нет матчей в статусе 'scheduled'.", reply_markup=kb_admin_ms_menu(tid))
        await cb.answer(); return
    rows = []
    for (mid, stage, h, a, sh, sa, st) in open_matches:
        label = f"{h} — {a}" + (f" ({stage})" if stage else "")
        rows.append([InlineKeyboardButton(text=label, callback_data=f"admin_ms_pickmatch:{mid}:{tid}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_ms:{tid}")])
    await cb.message.edit_text("Выбери матч:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()

@router.callback_query(F.data.startswith("admin_ms_pickmatch:"))
async def admin_ms_pickmatch(cb: CallbackQuery, state: FSMContext):
    _, mid, tid = cb.data.split(":")
    await state.update_data(_ms_mid=int(mid), _ms_tid=int(tid))
    await cb.message.edit_text("Введите счёт в формате A:B (например 21:17):")
    await cb.answer()
    await state.set_state(AdminMatches.score_wait_value)

@router.message(AdminMatches.score_wait_value)
async def admin_ms_score_input(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    data = await state.get_data()
    mid, tid = data.get("_ms_mid"), data.get("_ms_tid")
    try:
        a,b = text.split(":"); sh, sa = int(a), int(b)
        if sh<0 or sa<0 or sh>200 or sa>200: raise ValueError()
    except Exception:
        await message.answer("Неверный формат. Пример: 21:17"); return
    ms_save_score(mid, sh, sa)
    award_achievements_for_match(mid)

    # пересчёт агрегатов и рейтинга
    await recalc_player_stats_for_tournament(tid, user_id=None)
    await update_ratings_for_match(mid)

    await state.clear()
    await message.answer("💾 Сохранено.", reply_markup=kb_admin_ms_menu(tid))


# === SIMPLE RATING UPDATE (per finished match) ===
async def update_ratings_for_match(mid: int):
    """Обновляет player_ratings (глобально) и player_ratings_by_tournament по результатам конкретного матча."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        cur = await db.execute("""
            SELECT tournament_id, team_home_name, team_away_name, COALESCE(score_home,0), COALESCE(score_away,0), COALESCE(status,'')
            FROM matches_simple WHERE id=?
        """, (mid,))
        row = await cur.fetchone()
        if not row:
            return
        tid, home, away, sh, sa, status = row
        if status != "finished":
            return

        a_won = sh > sa
        b_won = sa > sh
        margin = abs(sh - sa)
        margin_bonus = (margin // MARGIN_BUCKET) * K_MARGIN_STEP if margin and (a_won or b_won) else 0

        # статы игроков именно ЭТОГО матча
        cur = await db.execute("""
            SELECT user_id, team_name, COALESCE(points,0), COALESCE(assists,0), COALESCE(blocks,0)
            FROM player_match_stats
            WHERE tournament_id=? AND match_id=?
        """, (tid, mid))
        rows = await cur.fetchall()
        if not rows:
            return

        # определяем топ-бомбардиров матча
        top_points = max((r[2] for r in rows), default=0)
        top_ids = {r[0] for r in rows if r[2] == top_points and top_points > 0}

        # группируем по командам
        team_rows = {home: [], away: []}
        for uid, team, pts, ast, blk in rows:
            if team == home:
                team_rows[home].append((uid, pts, ast, blk))
            elif team == away:
                team_rows[away].append((uid, pts, ast, blk))

        def team_bonus(team: str) -> int:
            if team == home:
                base = (K_WIN + margin_bonus) if a_won else (K_LOSS if b_won else 0)
            else:
                base = (K_WIN + margin_bonus) if b_won else (K_LOSS if a_won else 0)
            return base

        async def apply_for_team(team: str, did_win: bool):
            tb = team_bonus(team)
            for uid, pts, ast, blk in team_rows.get(team, []):
                indiv = pts * K_POINT + ast * K_AST + blk * K_BLK
                bonus_top = K_TOP_SCORER if uid in top_ids else 0
                dRP = tb + indiv + bonus_top

                # глобально
                cur1 = await db.execute("SELECT rating, games FROM player_ratings WHERE user_id=?", (uid,))
                pr = await cur1.fetchone()
                if pr:
                    await db.execute(
                        "UPDATE player_ratings SET rating=?, games=?, updated_at=datetime('now') WHERE user_id=?",
                        (pr[0] + dRP, pr[1] + 1, uid)
                    )
                else:
                    await db.execute(
                        "INSERT INTO player_ratings(user_id, rating, games, updated_at) VALUES(?,?,?,datetime('now'))",
                        (uid, 1000 + dRP, 1)
                    )

                # по турниру
                cur2 = await db.execute("""
                    SELECT rating, games FROM player_ratings_by_tournament
                    WHERE tournament_id=? AND user_id=?
                """, (tid, uid))
                prt = await cur2.fetchone()
                if prt:
                    await db.execute("""
                        UPDATE player_ratings_by_tournament SET rating=?, games=?
                        WHERE tournament_id=? AND user_id=?
                    """, (prt[0] + dRP, prt[1] + 1, tid, uid))
                else:
                    await db.execute("""
                        INSERT INTO player_ratings_by_tournament(tournament_id, user_id, rating, games)
                        VALUES(?,?,?,?)
                    """, (tid, uid, 1000 + dRP, 1))

        await apply_for_team(home, a_won)
        await apply_for_team(away, b_won)
        await db.commit()

@router.callback_query(F.data.startswith("live_finish:"))
async def live_finish(cb: CallbackQuery):
    mid = int(cb.data.split(":")[1])
    m = await _get_match(mid)
    if not m:
        await cb.answer("Матч не найден", show_alert=True); return

    async with db_lock:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("PRAGMA busy_timeout=5000;")
            await db.execute("UPDATE matches_simple SET status='finished' WHERE id=?", (mid,))
            await db.commit()
        # после закрытия матча можно пересчитать всем участникам
        await recalc_player_stats_for_tournament(m['tid'], user_id=None)
        await update_ratings_for_match(mid)  # +++ добавили рейтинг

    await cb.message.edit_text(_render_live_header(await _get_match(mid)) + "\n\n<b>Матч завершён.</b>", parse_mode="HTML", reply_markup=_kb_live_root(await _get_match(mid)))
    await cb.answer("Матч закрыт")


# Из списка матчей показываем карточки с кнопками
@router.callback_query(F.data.startswith("admin_ms_list:"))
async def admin_ms_list(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return

    try:
        tid = int(cb.data.split(":")[1])
    except Exception:
        await cb.answer("tid не распознан", show_alert=True); return

    rows = ms_list_matches(tid, only_open=False, limit=200)  # [(mid, stage, home, away, sh, sa, status), ...]
    if not rows:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_ms:{tid}"))
        await cb.message.edit_text("Пока нет матчей.", reply_markup=kb.as_markup())
        await cb.answer()
        return

    text = "📋 <b>Все матчи турнира</b>\n\n"
    kb = InlineKeyboardBuilder()

    for i, (mid, stage, home, away, sh, sa, st) in enumerate(rows, start=1):
        sh = sh or 0; sa = sa or 0
        line = f"{i}. {home} <b>{sh}:{sa}</b> {away}"
        if stage:
            line += f" · <i>{stage}</i>"
        line += f" · <code>{st}</code>\n"
        text += "• " + line

        # Кнопки с названием матча в подписи — видно к чему относятся
        kb.row(
            InlineKeyboardButton(text=f"🎮 LIVE · {home} vs {away}", callback_data=f"match_live:{mid}"),
        )
        kb.row(
            InlineKeyboardButton(text="✏️ Изменить счёт", callback_data=f"admin_ms_edit:{mid}:{tid}"),
            InlineKeyboardButton(text="❌ Удалить",        callback_data=f"admin_ms_delete:{mid}:{tid}")
        )
        if st != "finished":
            kb.row(InlineKeyboardButton(text="🏁 Завершить матч", callback_data=f"live_finish:{mid}"))

    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_ms:{tid}"))
    await cb.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("admin_ms_delete:"))
async def admin_ms_delete(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return

    try:
        _, mid, tid = cb.data.split(":")
        mid, tid = int(mid), int(tid)
    except Exception:
        await cb.answer("Данные не распознаны", show_alert=True); return

    # удаляем матч
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM matches_simple WHERE id=?", (mid,))
            await db.commit()
        await cb.answer("Матч удалён ✅")
    except Exception as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True)
        return

    # обновляем список
    await admin_ms_list(CallbackQuery(
        id=cb.id, from_user=cb.from_user, chat_instance=cb.chat_instance,
        message=cb.message, data=f"admin_ms_list:{tid}")
    )



# Правка счёта (повторно)
@router.callback_query(F.data.startswith("admin_ms_edit:"))
async def admin_ms_edit(cb: CallbackQuery, state: FSMContext):
    _, mid, tid = cb.data.split(":")
    await state.update_data(_ms_mid=int(mid), _ms_tid=int(tid))
    await cb.message.edit_text("Введите новый счёт в формате A:B (например 21:17):")
    await state.set_state(AdminMatches.score_wait_value)
    await cb.answer()

@router.callback_query(F.data == "open_admin")
async def open_admin(cb: CallbackQuery):
    # защита
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); 
        return

    # минимальная «корневая» клавиатура админки
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Турниры", callback_data="admin_tournaments")],
        # при желании сюда добавишь и другие пункты админки
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_user_menu")]
    ])
    await cb.message.edit_text("🔧 Админ-панель: выбери действие.", reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data == "back_to_user_menu")
async def back_to_user_menu(cb: CallbackQuery):
    await cb.message.edit_text("Выбери турнир:", reply_markup=kb_tournaments_list())
    await cb.answer()



# Тех.поражение (WO) — ставим 20:0 для хозяев по умолчанию, можно менять логику
@router.callback_query(F.data.startswith("admin_ms_wo:"))
async def admin_ms_wo(cb: CallbackQuery):
    _, mid, tid = cb.data.split(":")
    ms_save_score(int(mid), 20, 0)  # при желании сделаем выбор стороны позже
    award_achievements_for_match(int(mid))

    await cb.message.edit_text("⚠️ Проставлено тех.поражение (20:0).", reply_markup=kb_admin_ms_menu(int(tid)))
    await cb.answer()

# Удаление матча
@router.callback_query(F.data.startswith("admin_ms_delask:"))
async def admin_ms_delask(cb: CallbackQuery):
    _, mid, tid = cb.data.split(":")
    await cb.message.edit_text("Удалить этот матч?", reply_markup=kb_admin_ms_del_confirm(int(mid), int(tid)))
    await cb.answer()

@router.callback_query(F.data.startswith("admin_ms_del:"))
async def admin_ms_del(cb: CallbackQuery):
    _, mid, tid = cb.data.split(":")
    ms_delete_match(int(mid))
    await cb.message.edit_text("🗑 Матч удалён.", reply_markup=kb_admin_ms_menu(int(tid)))
    await cb.answer()

def ms_upcoming(tid:int, n:int=7):
    with db() as con:
        return con.execute("""SELECT team_home_name, team_away_name, stage
                              FROM matches_simple
                              WHERE tournament_id=? AND status='scheduled'
                              ORDER BY id ASC LIMIT ?""", (tid, n)).fetchall()



@router.callback_query(Form.waiting_for_team_status)
async def choose_status(callback: CallbackQuery, state: FSMContext):
    if callback.data == "has_team":
        await callback.message.answer(
            "🔐 Введи <b>код приглашения</b> твоей команды (6 символов, например <code>8K2RJD</code>):"
        )
        await state.set_state(Form.waiting_for_invite_code)

    elif callback.data == "new_team":
        await callback.message.answer("🆕 Напиши название новой команды:")
        await state.set_state(Form.waiting_for_team_name)

    elif callback.data == "free_agent":
        await callback.message.answer("📝 Напиши о себе:\n\n<em>Амплуа, возраст, рост, уровень игры</em>")
        await state.set_state(Form.waiting_for_free_info)

# Открыть список турниров
@router.callback_query(F.data == "choose_tournament")
async def choose_tournament(cb: CallbackQuery):
    await cb.message.edit_text("Выбери турнир:", reply_markup=kb_tournaments_list())
    await cb.answer()

@router.callback_query(F.data.startswith("open_tournament:"))
async def open_tournament(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    t = get_tournament_by_id(tid)
    if not t:
        await cb.answer("Турнир не найден", show_alert=True); return
    # подстраховка: не открываем архивный турнир
    if t[2] == "archived" and cb.from_user.id not in ADMINS:
        await cb.answer("Этот турнир в архиве.", show_alert=True)
        await cb.message.edit_text("Выбери турнир:", reply_markup=kb_tournaments_list())
        return

    set_user_current_tournament(cb.from_user.id, tid)
    caption = f"Меню «{t[1]}»"
    await cb.message.edit_text(caption, reply_markup=kb_tournament_menu(tid, cb.from_user.id))
    await cb.answer()

# Вернуться в глобальное меню



@router.callback_query(F.data.startswith("t_info:"))
async def t_info(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    await cb.message.edit_text("Выбери раздел:", reply_markup=kb_tinfo_sections(tid))
    await cb.answer()




@router.callback_query(F.data == "admin_tournaments")
async def admin_tournaments(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    await cb.message.edit_text("🏆 Турниры:", reply_markup=kb_admin_tournaments_list())
    await cb.answer()

def kb_admin_tournament_manage(tid:int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Переименовать",            callback_data=f"admin_tournament_rename:{tid}")],
        [InlineKeyboardButton(text="📅 Дата/место",                callback_data=f"admin_tournament_whenwhere:{tid}")],
        [InlineKeyboardButton(text="🚪 Открыть регистрацию",       callback_data=f"admin_tournament_open:{tid}")],
        [InlineKeyboardButton(text="🔒 Закрыть регистрацию",       callback_data=f"admin_tournament_close:{tid}")],
        [InlineKeyboardButton(text="ℹ️ Редактировать разделы Info",callback_data=f"admin_tinfo:{tid}")],
        [InlineKeyboardButton(text="👥 Команды турнира",           callback_data=f"admin_tt:{tid}")],
        [InlineKeyboardButton(text="📊 Матчи / Счёт",              callback_data=f"admin_ms:{tid}")],
        [InlineKeyboardButton(text="👁 Открыть как пользователь",  callback_data=f"open_tournament:{tid}")],
        [InlineKeyboardButton(text="🔗 Скопировать deep-link",     callback_data=f"admin_tournament_link:{tid}")],
        [InlineKeyboardButton(text="📦 Архивировать турнир",       callback_data=f"admin_tournament_archive:{tid}")],
        [InlineKeyboardButton(text="⬅️ К списку турниров",         callback_data="admin_tournaments")],
    ])



@router.callback_query(F.data.startswith("t_info_show:"))
async def t_info_show(cb: CallbackQuery):
    _, tid, key = cb.data.split(":")
    tid = int(tid)
    title = dict(SECTIONS).get(key, key)
    with db() as con:
        row = con.execute(
            "SELECT content FROM tournament_info WHERE tournament_id=? AND section=?",
            (tid, key)
        ).fetchone()
    content = row[0] if row and row[0] else "Раздел пока пуст."
    await cb.message.edit_text(f"<b>{title}</b>\n\n{content}", reply_markup=kb_tournament_menu(tid, cb.from_user.id))
    await cb.answer()

@router.callback_query(F.data.startswith("t_stats_menu:"))
async def t_stats_menu(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    await cb.message.edit_text("📊 Статистика турнира", reply_markup=kb_user_stats_menu(tid))
    await cb.answer()

@router.callback_query(F.data.startswith("t_stats:"))
async def t_stats(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    rows = standings_for_tournament(tid)
    if not rows:
        await cb.message.edit_text("Пока нет завершённых матчей.", reply_markup=kb_user_stats_menu(tid))
        await cb.answer(); return
    header = "Команда               И   W   L   PF   PA   +/-"
    lines = [header, "-"*len(header)]
    for team,g,w,l,pf,pa,diff in rows:
       lines.append(f"{team[:18]:<20}{g:>2}  {w:>2}  {l:>2}  {pf:>3}  {pa:>3}  {diff:>+3}")
    txt = "📊 Таблица\n\n" + "\n".join(lines)
    await cb.message.edit_text(txt, reply_markup=kb_user_stats_menu(tid))
    await cb.answer()

@router.callback_query(F.data.startswith("t_last:"))
async def t_last(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    res = ms_last_results(tid, n=7)
    if not res:
        await cb.message.edit_text("Завершённых матчей пока нет.", reply_markup=kb_user_stats_menu(tid))
        await cb.answer(); return
    lines = ["📅 Последние матчи\n"]
    for h,sh,sa,a,stage in res:
        lines.append(f"{h} {sh} — {sa} {a}" + (f" ({stage})" if stage else ""))
    await cb.message.edit_text("\n".join(lines), reply_markup=kb_user_stats_menu(tid))
    await cb.answer()

@router.callback_query(F.data == "ach_back")
async def ach_back(cb: CallbackQuery):
    """Возврат к общему экрану ачивок"""
    txt = (
        "🏅 *Система ачивок VZALE*\n"
        "_Выбирай уровень, чтобы посмотреть достижения:_\n\n"
        "🎯 *EASY* — для новичков\n"
        "⚡ *MEDIUM* — прояви себя\n"
        "👑 *HARD* — для постоянных\n"
        "💎 *ULTRA* — легендарные\n"
        "👕 *ULTIMATE* — мета-цель\n"
    )
    await cb.message.edit_text(
        txt,
        parse_mode="MarkdownV2",
        reply_markup=kb_achievements_menu()
    )
    await cb.answer()


@router.callback_query(F.data.startswith("t_register_team:"))
async def t_register_team(cb: CallbackQuery, state: FSMContext):
    tid = int(cb.data.split(":")[1])
    await state.update_data(_reg_tid=tid)
    await cb.message.edit_text("🆕 Введи название новой команды для этого турнира:")
    await state.set_state(Form.waiting_for_team_name_in_tournament)
    await cb.answer()

@router.message(Form.waiting_for_team_name_in_tournament)
async def create_team_for_tournament(message: Message, state: FSMContext):
    data = await state.get_data()
    tid = data.get("_reg_tid")
    team_name = (message.text or "").strip()
    user_id = message.from_user.id

    if not tid or not team_name:
        await state.clear()
        await message.answer("⚠️ Ошибка сессии. Попробуй заново из меню турнира.")
        return

    # 1) Добавим команду в справочник турнира (если нет)
    ok = tt_add_name(tid, team_name)
    if not ok:
        await state.clear()
        await message.answer("⚠️ Такая команда уже есть в этом турнире или имя пустое.", reply_markup=kb_tournament_menu(tid,cb.from_user.id))
        return

    # 2) Добавим пользователя в users/teams, если его там нет
    #    (чтобы он стал капитаном/первым участником; дубли не создаём)
    async with aiosqlite.connect(DB_PATH) as adb:
        cur = await adb.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))
        exists = await cur.fetchone() is not None
        if not exists:
            # если пользователь ещё не регистрировался — попросим имя из Form.waiting_for_name ?
            # На практике у тебя уже есть регистрация. Здесь сохраним базово.
            await adb.execute("INSERT INTO users(user_id, full_name, team) VALUES (?, ?, ?)",
                              (user_id, message.from_user.full_name or "Игрок", team_name))
        else:
            # обновим его команду (если пустая)
            await adb.execute("UPDATE users SET team = COALESCE(team, ?) WHERE user_id=? AND (team IS NULL OR team='')",
                              (team_name, user_id))

        # в состав команды добавим капитана, если его нет
        cur = await adb.execute("SELECT 1 FROM teams WHERE team_name=? AND member_id=?",
                                (team_name, user_id))
        if not (await cur.fetchone()):
            await adb.execute("INSERT INTO teams(team_name, member_id, member_name) VALUES(?,?,?)",
                              (team_name, user_id, message.from_user.full_name or 'Игрок'))

        await adb.commit()

    # 3) Сгенерируем/обновим код приглашения
    code = await ensure_team_code(team_name)

    name = tournament_label(tid)
    await notify_admins(
    f"🆕 <b>Команда в «{name}»:</b> {team_name}\n"
    f"👤 Капитан: {message.from_user.full_name}\n"
    f"🔐 Код приглашения: <code>{code}</code>"
)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 Показать/скопировать код", callback_data=f"show_invite:{team_name}")],
        [InlineKeyboardButton(text="⬅️ В меню турнира", callback_data=f"open_tournament:{tid}")]
    ])
    await message.answer(
        f"🎉 Команда <b>{team_name}</b> создана для турнира <b>{tid}</b>!\n\n"
        f"🔐 Код приглашения: <code>{code}</code>\n"
        f"Передай этот код однокомандникам.",
        reply_markup=kb
    )
    await state.clear()

def get_priority_tournament():
    tours = get_tournaments(active_only=True)  # (id, name, status)
    if not tours:
        return None
    # 1) открыта регистрация
    for t in tours:
        if t[2] == "registration_open":
            return t
    # 2) идёт турнир
    for t in tours:
        if t[2] == "running":
            return t
    # 3) иначе первый активный (они уже отсортированы DESC)
    return tours[0]


def award_achievement(team_name: str, tournament_id: int, code: str) -> bool:
    with db() as con:
        ach = con.execute("SELECT id FROM achievements WHERE code=?", (code,)).fetchone()
        if not ach:
            return False
        ach_id = ach[0]
        try:
            con.execute("""
                INSERT INTO team_achievements(team_name, tournament_id, achievement_id)
                VALUES(?,?,?)
            """, (team_name, tournament_id, ach_id))
            con.commit()
            return True
        except Exception:
            return False

def kb_leave_confirm(tid: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить выход", callback_data=f"t_leave_yes:{tid}")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"open_tournament:{tid}")]
    ])

def tournament_label(tid: int) -> str:
    t = get_tournament_by_id(tid)
    return t[1] if t and t[1] else f"Турнир #{tid}"


def list_team_achievements(tid:int, team_name:str):
    with db() as con:
        return con.execute("""SELECT a.emoji,a.title,a.description
                              FROM team_achievements ta
                              JOIN achievements a ON ta.achievement_id=a.id
                              WHERE ta.tournament_id=? AND ta.team_name=?""", (tid, team_name)).fetchall()


@router.callback_query(F.data.startswith("t_join:"))
async def t_join(cb: CallbackQuery, state: FSMContext):
    tid = int(cb.data.split(":")[1])
    await state.update_data(_join_tid=tid)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"open_tournament:{tid}")]
    ])
    await cb.message.edit_text("🔑 Введи код приглашения (6 символов):", reply_markup=kb)
    await state.set_state(Form.waiting_for_invite_code)
    await cb.answer()


@router.callback_query(F.data.startswith("t_free:"))
async def t_free(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    await cb.message.edit_text(f"🧑‍🚀 Свободный игрок для турнира ID {tid} ",
                               reply_markup=kb_tournament_menu(tid, cb.from_user.id))
    await cb.answer()

@router.callback_query(F.data.startswith("t_myteam:"))
async def t_myteam(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    user_id = cb.from_user.id

    # 1) Узнаём команду пользователя
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT team FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
    team_name = row[0] if row and row[0] else None

    if not team_name:
        await cb.answer("Ты пока не в команде.", show_alert=True)
        await cb.message.edit_text(
            f"Меню «{get_tournament_by_id(tid)[1]}»",
            reply_markup=kb_tournament_menu(tid, user_id)
        )
        return

    # 2) Получаем состав команды (ИЗ teams: member_id, member_name)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT member_id, member_name FROM teams WHERE team_name=?", (team_name,)
        )
        members_rows = await cur.fetchall()

    members = [(r[0], r[1]) for r in members_rows]
    members_text = "\n".join(f"{m[1]}" for m in members) if members else "пока пусто"

    # 3) Статус оплат — не валимся, если таблицы/полей нет
    team_paid, player_paid = None, None
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT team_paid, player_paid FROM payments WHERE tournament_id=? AND team_name=? AND user_id=?",
                (tid, team_name, user_id)
            )
            row = await cur.fetchone()
        if row:
            team_paid = 1 if row[0] else 0
            player_paid = 1 if row[1] else 0
    except Exception:
        # таблицы/колонок нет — просто показываем «неизвестно»
        team_paid = None
        player_paid = None

    def paid_badge(v):
        if v is None:
            return "—"
        return "✅ оплачен" if v else "❌ не оплачен"

    # 4) Текст
    text = (
        f"<b>👥 Моя команда (турнир {tid})</b>\n\n"
        f"🏷 Команда: <b>{team_name}</b>\n"
        f"💰 Командный взнос: {paid_badge(team_paid)}\n"
        f"💳 Твой личный взнос: {paid_badge(player_paid)}\n"
        f"🧑 Участники:\n{members_text}"
    )

    # 5) Ачивки (если у тебя есть функция)
    try:
        ach_list = list_team_achievements(tid, team_name)
        if ach_list:
            ach_text = "\n".join(f"{e} {t} — {d}" for e, t, d in ach_list)
        else:
            ach_text = "Ачивок пока нет"
        text += f"\n\n🏅 Ачивки:\n{ach_text}"
    except Exception:
        pass

    # 6) Клавиатура меню + кнопки удаления (не удаляем самого себя)
    extra_kb = kb_tournament_menu(tid, user_id)
    for uid, name in members:
        if uid == user_id:
            continue
        extra_kb.inline_keyboard.append(
            [InlineKeyboardButton(text=f"➖ Удалить {name}", callback_data=f"team_rm:{uid}")]
        )

    await cb.message.edit_text(text, reply_markup=extra_kb)
    await cb.answer()



@router.callback_query(F.data.startswith("rm:"))
async def team_remove_by_uid(cb: CallbackQuery):
    _, tid_s, uid_s = cb.data.split(":")
    tid = int(tid_s)
    remove_uid = int(uid_s)
    actor_uid = cb.from_user.id

    # узнаём команду текущего пользователя (актора)
    async with aiosqlite.connect(DB_PATH) as adb:
        cur = await adb.execute("SELECT team FROM users WHERE user_id=?", (actor_uid,))
        row = await cur.fetchone()
    if not row or not row[0]:
        await cb.answer("Ты не в команде.", show_alert=True); return

    team_name = row[0]

    if remove_uid == actor_uid:
        await cb.answer("Нельзя удалить самого себя.", show_alert=True); return

    # удаляем из состава и отвязываем в users, только если действительно из этой команды
    async with aiosqlite.connect(DB_PATH) as adb:
        # проверяем, что удаляемый состоит в этой команде
        cur = await adb.execute(
            "SELECT 1 FROM teams WHERE team_name=? AND member_id=?",
            (team_name, remove_uid)
        )
        if not await cur.fetchone():
            await cb.answer("Этот игрок не в твоей команде.", show_alert=True); return

        await adb.execute("DELETE FROM teams WHERE team_name=? AND member_id=?", (team_name, remove_uid))
        await adb.execute("UPDATE users SET team=NULL WHERE user_id=? AND team=?", (remove_uid, team_name))
        await adb.commit()

        # имя для сообщения
        cur = await adb.execute("SELECT full_name FROM users WHERE user_id=?", (remove_uid,))
        rr = await cur.fetchone()
        removed_name = rr[0] if rr and rr[0] else str(remove_uid)

    await cb.answer("Удалён ✅")
    # перерисуем экран "Моя команда" (покажет обновлённый состав и кнопки)
    await t_myteam(cb)

 

@router.callback_query(F.data.startswith("team_remove_member:"))
async def team_remove_member(cb: CallbackQuery):
    _, tid, member_name = cb.data.split(":", 2)
    tid = int(tid)

    with db() as con:
        con.execute("DELETE FROM teams WHERE team_name=(SELECT team FROM users WHERE user_id=?) AND member_name=?",
                    (cb.from_user.id, member_name))
        con.commit()

    await cb.answer(f"Игрок {member_name} удалён", show_alert=True)
    # обновляем экран "Моя команда"
    await t_myteam(cb)


@router.callback_query(F.data.startswith("confirm_remove:"))
async def confirm_remove(cb: CallbackQuery):
    _, team_id, remove_uid = cb.data.split(":")
    team_id, remove_uid = int(team_id), int(remove_uid)

    with db() as con:
        con.execute("UPDATE users SET team_id=NULL WHERE user_id=?", (remove_uid,))
        con.commit()
        team_name = con.execute("SELECT team_name FROM teams WHERE id=?", (team_id,)).fetchone()[0]

    await cb.message.edit_text(f"Игрок успешно удалён из команды {team_name}.", reply_markup=None)
    await cb.answer("Удалён ✅", show_alert=True)


def award_achievements_for_match(mid: int):
    with db() as con:
        match = con.execute("""
            SELECT tournament_id, team_home_name, team_away_name, score_home, score_away, status
            FROM matches_simple
            WHERE id=?
        """, (mid,)).fetchone()
        if not match:
            return

        tid, home, away, sh, sa, st = match
        if st != 'finished':
            return

        # 1) FIRST_WIN — первая победа
        if sh > sa:
            award_team_and_players(home, tid, "FIRST_WIN")
        elif sa > sh:
            award_team_and_players(away, tid, "FIRST_WIN")

        # 2) WIN_STREAK3 — серия из 3 побед подряд
        for team, score, opp_score in [(home, sh, sa), (away, sa, sh)]:
            if score > opp_score:
                row = con.execute("""
                    SELECT score_home, score_away, team_home_name, team_away_name
                    FROM matches_simple
                    WHERE tournament_id=? AND (team_home_name=? OR team_away_name=?) AND status='finished'
                    ORDER BY id DESC LIMIT 3
                """, (tid, team, team)).fetchall()
                if len(row) == 3 and all((r[0] > r[1] if r[2] == team else r[1] > r[0]) for r in row):
                    award_team_and_players(team, tid, "WIN_STREAK3")

        # 3) HUNDRED_POINTS — 100 очков суммарно
        for team in [home, away]:
            total = con.execute("""
                SELECT COALESCE(SUM(
                    CASE
                        WHEN team_home_name=? THEN score_home
                        WHEN team_away_name=? THEN score_away
                        ELSE 0
                    END
                ),0)
                FROM matches_simple
                WHERE tournament_id=? AND status='finished'
            """, (team, team, tid)).fetchone()[0] or 0
            if total >= 100:
                award_team_and_players(team, tid, "HUNDRED_POINTS")

        # 4) IRON_DEFENSE — пропустить < 10 очков и победить
        if sh > sa and sa < 10:
            award_team_and_players(home, tid, "IRON_DEFENSE")
        if sa > sh and sh < 10:
            award_team_and_players(away, tid, "IRON_DEFENSE")

        # 5) TEN_GAMES — сыграть 10 матчей
        for team in [home, away]:
            games = con.execute("""
                SELECT COUNT(*) FROM matches_simple
                WHERE tournament_id=? AND (team_home_name=? OR team_away_name=?) AND status='finished'
            """, (tid, team, team)).fetchone()[0]
            if games >= 10:
                award_team_and_players(team, tid, "TEN_GAMES")


@router.callback_query(F.data.startswith("team_remove_member:"))
async def team_remove_member(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    user_id = cb.from_user.id

    # узнаём команду пользователя
    async with aiosqlite.connect(DB_PATH) as adb:
        cur = await adb.execute("SELECT team FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
    if not row or not row[0]:
        await cb.answer("Ты не в команде.", show_alert=True); return

    team_name = row[0]

    # список участников этой команды (кроме самого пользователя)
    async with aiosqlite.connect(DB_PATH) as adb:
        cur = await adb.execute(
            "SELECT member_id, member_name FROM teams WHERE team_name=? AND member_id<>?",
            (team_name, user_id)
        )
        members = await cur.fetchall()

    if not members:
        await cb.answer("Удалять некого — в команде только ты.", show_alert=True); return

    # строим клавиатуру с участниками
    rows = [[InlineKeyboardButton(text=name, callback_data=f"team_rm:{mid}")]
            for (mid, name) in members]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"t_myteam:{tid}")])

    await cb.message.edit_text(
        f"Кого удалить из команды <b>{team_name}</b>?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await cb.answer()

@router.callback_query(F.data.startswith("team_rm:"))
async def team_rm(cb: CallbackQuery):
    remove_uid = int(cb.data.split(":")[1])
    user_id = cb.from_user.id

    # определим команду по автору действия
    async with aiosqlite.connect(DB_PATH) as adb:
        cur = await adb.execute("SELECT team FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
    if not row or not row[0]:
        await cb.answer("Ты не в команде.", show_alert=True); return

    team_name = row[0]

    # защитимся от случайного удаления себя
    if remove_uid == user_id:
        await cb.answer("Нельзя удалить самого себя.", show_alert=True); return

    # удаляем участника из состава и отвязываем его в users
    async with aiosqlite.connect(DB_PATH) as adb:
        await adb.execute("DELETE FROM teams WHERE team_name=? AND member_id=?", (team_name, remove_uid))
        await adb.execute("UPDATE users SET team=NULL WHERE user_id=? AND team=?", (remove_uid, team_name))
        await adb.commit()

        # узнаем имя для сообщения
        cur = await adb.execute("SELECT full_name FROM users WHERE user_id=?", (remove_uid,))
        r = await cur.fetchone()
        removed_name = r[0] if r and r[0] else str(remove_uid)

    await cb.message.edit_text(f"✅ Игрок <b>{removed_name}</b> удалён из команды <b>{team_name}</b>.",
                               reply_markup=kb_tournament_menu(int(getattr(cb, "tid", 0)) if False else None))
    # вернёмся в «Моя команда» заново, чтобы перечитать состав
    await t_myteam(cb)  # переиспользуем хендлер — он перерисует экран


@router.message(Form.waiting_for_team_name)
async def _new_team(message: Message, state: FSMContext):
    data = await state.get_data()
    team_name = message.text.strip()
    user_id = message.from_user.id
    full_name = data.get("full_name") or "Игрок"

    # генерируем уникальный код
    code = gen_invite_code(6)
    # на всякий случай проверим уникальность
    async with aiosqlite.connect(DB_PATH) as db:
        # если пользователь уже зарегистрирован — выходим
        if await user_exists(user_id):
            await message.answer("⚠️ Ты уже зарегистрирован.", reply_markup= kb_global(user_id))
            return

        # создаём пользователя и первую запись в составе
        await db.execute("INSERT INTO users (user_id, full_name, team) VALUES (?, ?, ?)", (user_id, full_name, team_name))
        await db.execute("INSERT INTO teams (team_name, member_id, member_name) VALUES (?, ?, ?)", (team_name, user_id, full_name))

        # создаём/заносим код приглашения для этой команды
        # если вдруг совпал код — перегенерируем
        unique = False
        attempts = 0
        while not unique and attempts < 10:
            try:
                await db.execute("INSERT INTO team_security (team_name, invite_code) VALUES (?, ?)", (team_name, code))
                unique = True
            except Exception:
                code = gen_invite_code(6)
                attempts += 1

        await db.commit()

    await notify_admins(
        f"🆕 <b>Новая команда:</b> {team_name}\n"
        f"👤 Капитан: {full_name}\n"
        f"🔐 Код приглашения: <code>{code}</code>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 Показать/скопировать код", callback_data=f"show_invite:{team_name}")]
    ])

    await message.answer(
        f"🎉 Команда <b>{team_name}</b> создана!\n\n"
        f"🔐 Код приглашения для игроков: <code>{code}</code>\n"
        f"Передай этот код твоим однокомандникам — они войдут в команду только по нему.\n\n"
        "Подпишись, чтобы ничего не пропустить:\n"
        "https://t.me/vzzale \nhttps://vk.com/vzale1 \nhttps://www.instagram.com/vzale_bb?igsh=Y2Y1Nmx5YTE4aWJp",
        reply_markup= kb_global(user_id)
    )
    await state.clear()
# ==== STATS TABLES INIT ====
def ensure_stats_tables_sqlite():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS tournament_team_names (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(tournament_id, name)
        );

        CREATE TABLE IF NOT EXISTS matches_simple (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            stage TEXT,
            team_home_name TEXT NOT NULL,
            team_away_name TEXT NOT NULL,
            score_home INTEGER,
            score_away INTEGER,
            status TEXT DEFAULT 'scheduled' -- scheduled|finished|wo
        );
        """)
        con.commit()


@router.callback_query(F.data.startswith("regen_code:"))
async def regen_code(callback: CallbackQuery):
    if callback.from_user.id not in ADMINS:
        await callback.message.answer("⛔️ Нет доступа.", reply_markup= kb_global(callback.from_user.id))
        return
    team_name = callback.data.split(":", 1)[1]
    # генерим новый и перезаписываем
    new_code = gen_invite_code(6)
    async with aiosqlite.connect(DB_PATH) as db:
        # следим за уникальностью
        unique = False
        attempts = 0
        while not unique and attempts < 10:
            try:
                await db.execute(
                    "INSERT INTO team_security (team_name, invite_code) VALUES (?, ?) "
                    "ON CONFLICT(team_name) DO UPDATE SET invite_code=excluded.invite_code",
                    (team_name, new_code)
                )
                await db.commit()
                unique = True
            except Exception:
                new_code = gen_invite_code(6); attempts += 1
    await callback.message.answer(f"♻️ Новый код для <b>{team_name}</b>: <code>{new_code}</code>")




@router.callback_query(F.data.startswith("show_invite:"))
async def show_invite(callback: CallbackQuery):
    team_name = callback.data.split(":", 1)[1]
    code = await ensure_team_code(team_name)  # ← вместо ручного SELECT + "не найден"
    await callback.message.answer(f"🔐 Код команды <b>{team_name}</b>: <code>{code}</code>")


@router.callback_query(F.data == "suggest_feature")
async def suggest_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "💡 Напиши одним сообщением твою идею или опиши проблему.\n\n"
        "<b>Подсказка:</b> укажи, где именно в боте это происходит и как воспроизвести."
    )
    await state.set_state(SuggestionForm.waiting_text)

@router.message(SuggestionForm.waiting_text)
async def suggest_collect(message: Message, state: FSMContext):
    text = (message.html_text or message.text or "").strip()
    if len(text) < 10:
        await message.answer("⚠️ Слишком коротко. Опиши подробнее (минимум 10 символов).")
        return

    user_id = message.from_user.id
    # 1) Сохраняем в БД
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO suggestions (user_id, text) VALUES (?, ?)",
            (user_id, text)
        )
        await db.commit()
        suggestion_id = cur.lastrowid

    # 2) Сообщаем пользователю
    await message.answer(
        f"✅ Спасибо! Твоя идея/сообщение зарегистрирована под № <b>{suggestion_id}</b>.\n"
        "Мы посмотрим и вернёмся с ответом."
    )

    # 3) Оповещаем админов с кнопками действий
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✉️ Ответить", callback_data=f"suggest_reply:{suggestion_id}:{user_id}"),
        InlineKeyboardButton(text="✅ Готово",   callback_data=f"suggest_done:{suggestion_id}")
    ]])
    for admin_id in ADMINS:
        try:
            await bot.send_message(
                admin_id,
                text=(
                    "📨 <b>Новая идея/репорт</b>\n"
                    f"ID: <code>{suggestion_id}</code>\n"
                    f"От: <code>{user_id}</code>\n\n"
                    f"{text}"
                ),
                reply_markup=admin_kb
            )
        except Exception as e:
            logging.warning(f"Не удалось отправить идею админу {admin_id}: {e}")

    await state.clear()

@router.message(Form.waiting_for_invite_code)
async def join_by_code(message: Message, state: FSMContext):
    """
    Присоединение к команде по инвайт-коду в контексте выбранного турнира.
    Делает:
      - валидирует код
      - проверяет, не состоит ли игрок уже в этой команде
      - обновляет users.team, добавляет запись в teams (состав)
      - фиксирует состав турнира в tournament_roster (для ачивок игроков)
      - показывает меню турнира
    """
    code = (message.text or "").strip().upper()
    data = await state.get_data()
    tid = data.get("_join_tid")
    uid = message.from_user.id

    if not tid:
        await message.answer("Не выбран турнир. Откройте нужный турнир и попробуйте снова.")
        await state.clear()
        return

    # найти команду по коду
    team_name = await get_team_by_code(code)
    if not team_name:
        await message.answer("❌ Код не найден. Проверь и отправь ещё раз.")
        return

    safe_team = html.escape(team_name)

    async with aiosqlite.connect(DB_PATH) as db:
        # уже в этой команде?
        cur = await db.execute(
            "SELECT 1 FROM teams WHERE team_name=? AND member_id=? LIMIT 1",
            (team_name, uid)
        )
        if await cur.fetchone():
            await state.clear()
            await message.answer(
                f"Ты уже зарегистрирован в команде <b>{safe_team}</b> ✅",
                reply_markup=kb_tournament_menu(tid, uid),
            )
            return

        # users: обновляем команду
        await db.execute(
            "INSERT INTO users(user_id, full_name, team) VALUES (?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET full_name=excluded.full_name, team=excluded.team",
            (uid, message.from_user.full_name or "Игрок", team_name)
        )

        # teams: добавляем участника (список состава)
        await db.execute(
            "INSERT INTO teams(team_name, member_id, member_name) VALUES (?,?,?)",
            (team_name, uid, message.from_user.full_name or "Игрок")
        )

        # tournament_roster: фиксируем участие именно в этом турнире
        await db.execute(
            "INSERT OR IGNORE INTO tournament_roster(tournament_id, team_name, user_id, full_name) "
            "VALUES(?,?,?,?)",
            (tid, team_name, uid, message.from_user.full_name or "Игрок")
        )

        await db.commit()

    await state.clear()
    await message.answer(
        f"✅ Ты успешно присоединился к команде <b>{safe_team}</b>!",
        reply_markup=kb_tournament_menu(tid, uid),
    )



@router.callback_query(Form.waiting_for_team_selection, F.data.startswith("join_team"))
async def join_team(callback: CallbackQuery, state: FSMContext):
    team_name = callback.data.split(":")[1]
    user_id = callback.from_user.id
    data = await state.get_data()
    full_name = data.get("full_name", "Игрок")
    async with aiosqlite.connect(DB_PATH) as db:
        if await user_exists(user_id):
            await callback.message.answer("⚠️ Ты уже зарегистрирован.", reply_markup= kb_global(user_id))
            return
        await db.execute("INSERT INTO users (user_id, full_name, team) VALUES (?, ?, ?)", (user_id, full_name, team_name))
        await db.execute("INSERT INTO teams (team_name, member_id, member_name) VALUES (?, ?, ?)", (team_name, user_id, full_name))
        await db.commit()
    await notify_admins(f"👤 <b>Новый игрок присоединился к команде:</b>\n<b>{team_name}</b>\n🧍 {full_name}")
    await callback.message.answer(f"✅ Ты добавлен в команду <b>{team_name}</b>!\n\nПодпишись чтобы ничего не пропустить:\n https://t.me/vzzale \n https://vk.com/vzale1 \n https://www.instagram.com/vzale_bb?igsh=Y2Y1Nmx5YTE4aWJp", reply_markup= kb_global(user_id))
    await state.clear()

@router.callback_query(F.data == "leave_free_agents")
async def leave_free_agents(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM free_agents WHERE user_id = ?", (user_id,))
        await db.commit()

    await callback.message.answer("✅ Твоя анкета свободного игрока удалена.(Если хочешь добавиться в команду, то введи /start)", reply_markup= kb_global(user_id))

@router.callback_query(F.data == "my_team")
async def show_my_team(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT team FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            await callback.message.answer("🚫 Ты пока не в команде.", reply_markup= kb_global(user_id))
            return
        team_name = row[0]
        cursor = await db.execute("SELECT member_name FROM teams WHERE team_name = ?", (team_name,))
        members = await cursor.fetchall()
        names = "\n".join([f"• {m[0]}" for m in members])
        await callback.message.answer(f"<b>🏀 Твоя команда: {team_name}</b>\n\n👥 Участники:\n{names}", reply_markup= kb_global(user_id))

@router.callback_query(F.data == "list_teams")
async def show_teams(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT DISTINCT team_name FROM teams")
        teams = await cursor.fetchall()
        if not teams:
            await callback.message.answer("🚫 Пока нет зарегистрированных команд.", reply_markup= kb_global(callback.from_user.id))
            return
        text = "<b>📒 Список команд:</b>\n\n"
        for row in teams:
            team = row[0]
            cursor = await db.execute("SELECT member_name FROM teams WHERE team_name = ?", (team,))
            members = await cursor.fetchall()
            members_text = "\n ".join([m[0] for m in members])
            text += f"🏷 <b>{team}</b>:\n {members_text}\n"
        await callback.message.answer(text, reply_markup= kb_global(callback.from_user.id))

@router.callback_query(F.data == "free_agents")
async def show_free_agents(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMINS:
        await callback.message.answer("⛔️ Доступ запрещён.", reply_markup= kb_global(user_id))
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT name, info FROM free_agents")
        agents = await cursor.fetchall()
        if not agents:
            await callback.message.answer("📭 Список свободных игроков пуст.", reply_markup= kb_global(user_id))
            return
        text = "<b>🧍 Свободные игроки:</b>\n\n"
        for name, info in agents:
            text += f"• <b>{name}</b>\n{info}\n\n"
        await callback.message.answer(text, reply_markup= kb_global(user_id))

@router.message(Form.waiting_for_free_info)
async def handle_free_agent_info(message: Message, state: FSMContext):
    data = await state.get_data()
    name = data.get("full_name", "Без имени")
    info = message.text.strip()

    async with aiosqlite.connect(DB_PATH) as db:
        user_id = message.from_user.id
        await db.execute("INSERT INTO free_agents (user_id, name, info) VALUES (?, ?, ?)", (user_id, name, info))
        await db.commit()
    await notify_admins(f"🧍 <b>Новый свободный игрок:</b>\n👤 {name}\n📋 {info}")

    await message.answer("🧍 Ты добавлен в список свободных игроков!", reply_markup= kb_global(message.from_user.id))
    await state.clear()

@router.callback_query(F.data == "delete_profile")
async def delete_profile(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        # Удаляем из всех таблиц
        await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM teams WHERE member_id = ?", (user_id,))
        await db.execute("DELETE FROM free_agents WHERE user_id = ?", (user_id,))
        await db.commit()
    await callback.message.answer("🗑 Твой профиль был удалён. Чтобы пройти регистрацию заново — введи /start")

@router.callback_query(F.data == "leave_team")
async def leave_team(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        # Получаем команду пользователя
        cursor = await db.execute("SELECT team FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()

        if not row or not row[0]:
            await callback.message.answer("❌ Ты не состоишь ни в одной команде.", reply_markup= kb_global(user_id))
            return

        team = row[0]

        # Удаляем пользователя из команды
        await db.execute("UPDATE users SET team = NULL WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM teams WHERE member_id = ?", (user_id,))
        await db.commit()

    await callback.message.answer(f"🚪 Ты вышел из команды <b>{team}</b>.", reply_markup= kb_global(user_id))

@router.callback_query(F.data == "rejoin_team")
async def rejoin_team(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT full_name FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()

    if not row:
        await callback.message.answer("❗️Произошла ошибка: твои данные не найдены в базе.")
        return

    full_name = row[0]
    await state.update_data(full_name=full_name)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, я в команде (уже есть команда)", callback_data="has_team")],
        [InlineKeyboardButton(text="🆕 Хочу зарегистрировать команду", callback_data="new_team")],
        [InlineKeyboardButton(text="🧍 Я свободный игрок", callback_data="free_agent")]
    ])

    await callback.message.answer("🔁 Ты хочешь снова присоединиться?\n\nВыбери один из вариантов:", reply_markup=markup)
    await state.set_state(Form.waiting_for_team_status)

# ======================
#        АДМИНКА
# ======================

def admin_menu_markup():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🗑 Удалить команды", callback_data="admin_delete_teams"))
    kb.row(InlineKeyboardButton(text="🏆 Турниры", callback_data="admin_tournaments"))
    kb.row(InlineKeyboardButton(text="🎖 Выдать ачивку (за всё время)", callback_data="ach_admin_global"))
    kb.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    kb.row(InlineKeyboardButton(text="📊 Опрос", callback_data="admin_poll"))
    kb.row(InlineKeyboardButton(text="📈 Результаты опроса", callback_data="admin_poll_results"))  # ← новое
    kb.row(InlineKeyboardButton(text="⛔️ Закрыть опрос", callback_data="admin_poll_close")) 
    kb.row(InlineKeyboardButton(text="📋 Список команд", callback_data="list_teams"))  
    kb.row(InlineKeyboardButton(text="📮 Идеи/ошибки", callback_data="admin_suggestions"))
    kb.row(InlineKeyboardButton(text="♻️ Бэкфилл автоачивок", callback_data="ach_backfill_auto"))

     # ← новое
    kb.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="admin_back_to_menu"))
    return kb.as_markup()

@router.callback_query(F.data == "ach_backfill_auto")
async def ach_backfill_auto(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return

    # Диагностика: сколько турниров и команд видим
    tours = await _all_tournaments()
    diag_lines = [f"Найдено турниров: {len(tours)}"]
    for tid, name, status in tours:
        teams = await _teams_in_tournament(tid)
        diag_lines.append(f"• {name} (id={tid}, {status}) — команд: {len(teams)}")
    diag = "\n".join(diag_lines)

    res = await backfill_auto_achievements()  # {'FIRST_MATCH': 24, ...}

    if not res:
        await cb.message.answer(f"♻️ Бэкфилл автоачивок завершён.\nНовых начислений не найдено.\n\n{diag}")
        await cb.answer("Готово ✅")
        return

    lines = ["♻️ Бэкфилл автоачивок — готово.", ""]
    for code, cnt in sorted(res.items()):
        if cnt > 0:
            lines.append(f"• <b>{code}</b>: +{cnt}")
    lines.append("")
    lines.append(diag)
    await cb.message.answer("\n".join(lines), parse_mode="HTML")
    await cb.answer("Готово ✅")



@router.callback_query(F.data == "ach_backfill_global")
async def ach_backfill_global(cb: CallbackQuery):
    """Автоматически проставляет глобальные ачивки всем игрокам, у которых они уже есть в турнирах"""
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True)
        return

    added = await backfill_global_from_existing()

    text = f"♻️ Бэкфилл завершён.\nДобавлено записей: <b>{added}</b>"
    await cb.message.answer(text, parse_mode="HTML")
    await cb.answer("Готово ✅")


async def backfill_global_from_existing() -> int:
    """
    Проставляет базовые глобальные ачивки всем зарегистрированным игрокам
    и дублирует уже существующие ачивки из турниров в глобальные (tournament_id = 0).
    """
    added = 0
    async with aiosqlite.connect(DB_PATH) as db:
        # ---- 1. базовые ачивки: "зарегистрировался"
        # найдём всех, кто есть в users
        cur = await db.execute("SELECT DISTINCT user_id FROM users WHERE team IS NOT NULL")
        user_ids = [r[0] for r in await cur.fetchall()]

        # id ачивки (по коду)
        cur = await db.execute("SELECT id FROM achievements WHERE code IN ('FIRST_TEAM','REGISTERED') LIMIT 1")
        ach_row = await cur.fetchone()
        base_ach_id = ach_row[0] if ach_row else None

        if base_ach_id:
            for uid in user_ids:
                try:
                    await db.execute("""
                        INSERT INTO player_achievements(tournament_id, user_id, achievement_id)
                        VALUES(0, ?, ?)
                    """, (uid, base_ach_id))
                    added += 1
                except Exception:
                    pass

        # ---- 2. копирование существующих (как раньше)
        cur = await db.execute("""
            SELECT DISTINCT pa.user_id, pa.achievement_id
            FROM player_achievements pa
            WHERE pa.tournament_id <> 0
              AND NOT EXISTS (
                  SELECT 1 FROM player_achievements g
                  WHERE g.tournament_id = 0
                    AND g.user_id = pa.user_id
                    AND g.achievement_id = pa.achievement_id
              )
        """)
        rows = await cur.fetchall()
        for uid, ach_id in rows:
            try:
                await db.execute("""
                    INSERT INTO player_achievements(tournament_id, user_id, achievement_id)
                    VALUES(0, ?, ?)
                """, (uid, ach_id))
                added += 1
            except Exception:
                pass

        await db.commit()
    return added


@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMINS:
        await callback.message.answer("⛔️ Нет доступа.", reply_markup= kb_global(user_id))
        return
    await callback.message.answer("<b>🛠 Админ-панель</b>\nВыбери действие:", reply_markup=admin_menu_markup())

async def roster_with_names(tournament_id: int, team_name: str) -> list[tuple[int,str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT tr.user_id,
                   COALESCE(tr.full_name,
                            (SELECT u.full_name FROM users u WHERE u.user_id=tr.user_id),
                            'Игрок') AS name
            FROM tournament_roster tr
            WHERE tr.tournament_id=? AND tr.team_name=?
            ORDER BY name COLLATE NOCASE
        """, (tournament_id, team_name))
        return await cur.fetchall()

@router.callback_query(F.data.startswith("admin_ach:"))
async def admin_ach_menu(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    tid = int(cb.data.split(":")[1])
    names = tt_list_names(tid)
    rows = [[InlineKeyboardButton(text=name, callback_data=f"ach_team_pick:{tid}:{name}")] for name in names]
    # бэкфилл кнопка
    rows.append([InlineKeyboardButton(text="♻️ Бэкфилл из командных ачивок", callback_data=f"ach_backfill:{tid}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_tournament:{tid}")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await cb.message.edit_text(f"🎖 Управление ачивками · турнир {get_tournament_by_id(tid)[1]}", reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data.startswith("ach_team_pick:"))
async def ach_team_pick(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    _, tid, team = cb.data.split(":", 2)
    tid = int(tid)
    users = await roster_with_names(tid, team)
    if not users:
        await cb.answer("В ростере этой команды пока пусто", show_alert=True); return
    rows = [[InlineKeyboardButton(text=name, callback_data=f"ach_player:{tid}:{uid}")] for uid, name in users]
    rows.append([InlineKeyboardButton(text="⬅️ Назад к командам", callback_data=f"admin_ach:{tid}")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await cb.message.edit_text(f"Команда: {team}\nВыбери игрока:", reply_markup=kb)
    await cb.answer()

async def _achievements_for_user(tid:int, uid:int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT a.code, COALESCE(a.emoji,'•'), a.title, a.tier,
                   CASE WHEN pa.user_id IS NULL THEN 0 ELSE 1 END AS done
            FROM achievements a
            LEFT JOIN player_achievements pa
              ON pa.achievement_id=a.id AND pa.tournament_id=? AND pa.user_id=?
            ORDER BY CASE a.tier
                WHEN 'easy' THEN 1 WHEN 'medium' THEN 2 WHEN 'hard' THEN 3
                WHEN 'ultra' THEN 4 WHEN 'ultimate' THEN 5 ELSE 9 END,
                a.order_index, a.title COLLATE NOCASE
        """, (tid, uid))
        return await cur.fetchall()

@router.callback_query(F.data.startswith("ach_player:"))
async def ach_player(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    _, tid, uid = cb.data.split(":")
    tid, uid = int(tid), int(uid)

    rows = await _achievements_for_user(tid, uid)
    done = [r for r in rows if r[4]==1]
    notdone = [r for r in rows if r[4]==0]

    name = ""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT full_name FROM users WHERE user_id=?", (uid,))
        r = await cur.fetchone(); name = (r[0] if r and r[0] else f"ID {uid}")

    text = f"Игрок: *{esc_md2(name)}*\nТурнир: *{esc_md2(get_tournament_by_id(tid)[1])}*\n\n"
    text += "*Выполнено:*\n" + ("\n".join([f"✅ {x[1]} *{esc_md2(x[2])}*" for x in done]) if done else "—") + "\n\n"
    text += "*Не выполнено:*\n" + ("\n".join([f"⬜️ {x[1]} *{esc_md2(x[2])}*" for x in notdone]) if notdone else "—")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Выдать", callback_data=f"ach_grant_list:{tid}:{uid}")],
        [InlineKeyboardButton(text="🗑 Снять",  callback_data=f"ach_revoke_list:{tid}:{uid}")],
        [InlineKeyboardButton(text="⬅️ Назад к командам", callback_data=f"admin_ach:{tid}")]
    ])
    await cb.message.edit_text(text, parse_mode="MarkdownV2", reply_markup=kb)
    await cb.answer()

async def _all_achievements() -> list[tuple[str,str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT code, COALESCE(emoji,'')||' '||title
            FROM achievements
            ORDER BY CASE tier WHEN 'easy' THEN 1 WHEN 'medium' THEN 2 WHEN 'hard' THEN 3 WHEN 'ultra' THEN 4 WHEN 'ultimate' THEN 5 ELSE 9 END,
                     order_index, title
        """)
        return await cur.fetchall()

@router.callback_query(F.data.startswith("ach_grant_list:"))
async def ach_grant_list(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    _, tid, uid = cb.data.split(":"); tid=int(tid); uid=int(uid)
    rows = await _achievements_for_user(tid, uid)
    notdone = [(r[0], f"{r[1]} {r[2]}") for r in rows if r[4]==0]
    if not notdone:
        await cb.answer("Нет доступных для выдачи — все выполнены", show_alert=True); return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=title, callback_data=f"ach_grant:{tid}:{uid}:{code}")]
        for code, title in notdone
    ] + [[InlineKeyboardButton(text="⬅️ Назад", callback_data=f"ach_player:{tid}:{uid}")]])
    await cb.message.edit_text("Выбери ачивку для выдачи:", reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data.startswith("ach_revoke_list:"))
async def ach_revoke_list(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    _, tid, uid = cb.data.split(":"); tid=int(tid); uid=int(uid)
    rows = await _achievements_for_user(tid, uid)
    done = [(r[0], f"{r[1]} {r[2]}") for r in rows if r[4]==1]
    if not done:
        await cb.answer("Снимать нечего — нет выполненных", show_alert=True); return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=title, callback_data=f"ach_revoke:{tid}:{uid}:{code}")]
        for code, title in done
    ] + [[InlineKeyboardButton(text="⬅️ Назад", callback_data=f"ach_player:{tid}:{uid}")]])
    await cb.message.edit_text("Выбери ачивку для снятия:", reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data.startswith("ach_grant:"))
async def ach_grant(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    _, tid, uid, code = cb.data.split(":"); tid=int(tid); uid=int(uid)
    ok = await award_player_achievement(tid, uid, code, awarded_by=cb.from_user.id)
    await cb.answer("Выдано ✅" if ok else "Уже было", show_alert=False)
    await ach_player(cb)  # перерисуем экран

@router.callback_query(F.data.startswith("ach_revoke:"))
async def ach_revoke(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    _, tid, uid, code = cb.data.split(":"); tid=int(tid); uid=int(uid)
    ok = await revoke_player_achievement(tid, uid, code)
    await cb.answer("Снято 🗑" if ok else "Не было", show_alert=False)
    await ach_player(cb)  # перерисуем экран

async def backfill_players_from_team_achievements(tid:int) -> int:
    """Переносит все командные ачивки турнира tid в player_achievements всем игрокам ростера этих команд.
       Возвращает число добавленных записей."""
    added = 0
    async with aiosqlite.connect(DB_PATH) as db:
        # team_achievements → (team_name, achievement_id)
        cur = await db.execute("""
            SELECT team_name, achievement_id
            FROM team_achievements
            WHERE tournament_id=?
        """, (tid,))
        rows = await cur.fetchall()
        for team_name, ach_id in rows:
            # roster пользователей
            cur2 = await db.execute("""
                SELECT user_id FROM tournament_roster
                WHERE tournament_id=? AND team_name=?
            """, (tid, team_name))
            uids = [r[0] for r in await cur2.fetchall()]
            for uid in uids:
                try:
                    await db.execute("""
                        INSERT INTO player_achievements(tournament_id, user_id, achievement_id)
                        VALUES(?,?,?)
                    """, (tid, uid, ach_id))
                    added += 1
                except Exception:
                    pass
        await db.commit()
    return added

@router.callback_query(F.data.startswith("ach_backfill:"))
async def ach_backfill(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    tid = int(cb.data.split(":")[1])
    cnt = await backfill_players_from_team_achievements(tid)
    await cb.answer(f"Бэкфилл: +{cnt}", show_alert=True)

# ========= LIVE MATCH (per-player) =========
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- helpers ---

async def _get_match(mid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT id, tournament_id, team_home_name, team_away_name, score_home, score_away, COALESCE(status,'')
            FROM matches_simple WHERE id=?
        """, (mid,))
        row = await cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "tid": row[1],
        "home": row[2], "away": row[3],
        "sh": row[4] or 0, "sa": row[5] or 0,
        "status": row[6]
    }

async def _roster_with_names_live(tid:int, team:str) -> list[tuple[int,str]]:
    """Ростер для лайва: tournament_roster → teams → users.team (фолбэки)."""
    async with aiosqlite.connect(DB_PATH) as db:
        # 1) roster
        cur = await db.execute("""
            SELECT user_id, COALESCE(full_name,
                    (SELECT u.full_name FROM users u WHERE u.user_id=tr.user_id),'Игрок')
            FROM tournament_roster tr WHERE tournament_id=? AND team_name=?
            ORDER BY 2 COLLATE NOCASE
        """, (tid, team))
        rows = await cur.fetchall()
        if rows: return [(r[0], r[1]) for r in rows]
        # 2) teams (исторические)
        cur = await db.execute("""
            SELECT DISTINCT member_id, COALESCE(member_name,'Игрок')
            FROM teams WHERE team_name=? ORDER BY 2 COLLATE NOCASE
        """, (team,))
        rows = await cur.fetchall()
        if rows: return [(r[0], r[1]) for r in rows]
        # 3) users.team
        cur = await db.execute("""
            SELECT user_id, COALESCE(full_name,'Игрок')
            FROM users WHERE team=? ORDER BY 2 COLLATE NOCASE
        """, (team,))
        rows = await cur.fetchall()
        return [(r[0], r[1]) for r in rows]

async def _add_stats(tid: int, mid: int, team: str, uid: int, **inc):
    """
    Обновляет статистику игрока в матче (очки, подборы, ассисты и т.д.)
    tid — id турнира
    mid — id матча
    team — название команды
    uid — id игрока (user_id)
    inc — словарь {параметр: изменение}
    """

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")

        # Получаем текущие значения статистики
        cur = await db.execute("""
            SELECT points, threes, assists, rebounds, steals, blocks, fouls, turnovers, minutes
            FROM player_match_stats
            WHERE tournament_id=? AND match_id=? AND user_id=?
        """, (tid, mid, uid))
        row = await cur.fetchone()

        # Базовые показатели
        base = dict(
            points=0, threes=0, assists=0, rebounds=0, steals=0,
            blocks=0, fouls=0, turnovers=0, minutes=0
        )

        # Если запись существует — обновляем базу текущими данными
        if row:
            base.update(dict(
                points=row[0] or 0,
                threes=row[1] or 0,
                assists=row[2] or 0,
                rebounds=row[3] or 0,
                steals=row[4] or 0,
                blocks=row[5] or 0,
                fouls=row[6] or 0,
                turnovers=row[7] or 0,
                minutes=row[8] or 0
            ))

        # Добавляем инкременты (например +2 очка, +1 ассист)
        for k, v in inc.items():
            base[k] = max(0, int(base.get(k, 0)) + int(v))

    # Обновляем запись игрока
    await upsert_player_match_stats(tid, mid, team, uid, **base)

    # Пересчитываем личную статистику игрока (только его)
    await recalc_player_stats_for_tournament(tid, user_id=uid)


async def _inc_match_score(mid:int, side:str, val:int):
    """side: 'H'|'A'"""

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")

        if side == 'H':
            await db.execute("UPDATE matches_simple SET score_home = COALESCE(score_home,0) + ? WHERE id=?", (val, mid))
        else:
            await db.execute("UPDATE matches_simple SET score_away = COALESCE(score_away,0) + ? WHERE id=?", (val, mid))
        await db.commit()

def _kb_live_root(m) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🏀 Очки", callback_data=f"live_pts:{m['id']}"))
    kb.row(
        InlineKeyboardButton(text="🎯 Ассист", callback_data=f"live_evt:{m['id']}:assists"),
        InlineKeyboardButton(text="🧱 Подбор", callback_data=f"live_evt:{m['id']}:rebounds"),
    )
    kb.row(
      
        InlineKeyboardButton(text="🧱 Блок-шот", callback_data=f"live_evt:{m['id']}:blocks"),
    )
    kb.row(
        InlineKeyboardButton(text="⛔️ Фол", callback_data=f"live_evt:{m['id']}:fouls"),
        
    )
    kb.row(InlineKeyboardButton(text="🔄 Обновить", callback_data=f"match_live:{m['id']}"))
    kb.row(InlineKeyboardButton(text="🏁 Завершить матч", callback_data=f"live_finish:{m['id']}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_ms_list:{m['tid']}"))

    return kb.as_markup()

def _render_live_header(m) -> str:
    return (f"🏀 <b>LIVE-матч</b>\n"
            f"{html.escape(m['home'])} <b>{m['sh']}</b> — <b>{m['sa']}</b> {html.escape(m['away'])}\n"
            f"Статус: {html.escape(m['status'])}")

# --- open/refresh live ---

@router.callback_query(F.data.startswith("match_live:"))
async def match_live_open(cb: CallbackQuery):
    mid = int(cb.data.split(":")[1])
    m = await _get_match(mid)
    if not m:
        await cb.answer("Матч не найден", show_alert=True); return
    await cb.message.edit_text(_render_live_header(m), reply_markup=_kb_live_root(m), parse_mode="HTML")
    await cb.answer()

# --- points flow: pick team → pick value → pick scorer → optional assist ---

@router.callback_query(F.data.startswith("live_pts:"))
async def live_pts_pick_team(cb: CallbackQuery):
    mid = int(cb.data.split(":")[1])
    m = await _get_match(mid)
    if not m: 
        await cb.answer("Матч не найден", show_alert=True); return
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=f"🏠 {m['home']}", callback_data=f"live_pts_team:{mid}:H"))
    kb.row(InlineKeyboardButton(text=f"🧳 {m['away']}", callback_data=f"live_pts_team:{mid}:A"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"match_live:{mid}"))
    await cb.message.edit_text(_render_live_header(m) + "\n\nВыбери команду для очков:", reply_markup=kb.as_markup(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("live_pts_team:"))
async def live_pts_pick_value(cb: CallbackQuery):
    _, mid, side = cb.data.split(":")
    mid = int(mid)
    m = await _get_match(mid)
    if not m: 
        await cb.answer("Матч не найден", show_alert=True); return
    kb = InlineKeyboardBuilder()
    for v in (1,2,3):
        kb.row(InlineKeyboardButton(text=f"+{v}", callback_data=f"live_pts_val:{mid}:{side}:{v}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"live_pts:{mid}"))
    await cb.message.edit_text(_render_live_header(m) + "\n\nСколько очков начислить?", reply_markup=kb.as_markup(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("live_pts_val:"))
async def live_pts_pick_scorer(cb: CallbackQuery):
    _, mid, side, val = cb.data.split(":")
    mid = int(mid); val = int(val)
    m = await _get_match(mid)
    if not m: 
        await cb.answer("Матч не найден", show_alert=True); return
    team = m['home'] if side=='H' else m['away']
    roster = await _roster_with_names_live(m['tid'], team)
    if not roster:
        await cb.answer("Состав команды пуст", show_alert=True); return
    kb = InlineKeyboardBuilder()
    for uid, name in roster:
        kb.row(InlineKeyboardButton(text=name, callback_data=f"live_pts_scored:{mid}:{side}:{val}:{uid}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"live_pts_team:{mid}:{side}"))
    await cb.message.edit_text(_render_live_header(m) + f"\n\nКто забил +{val} за <b>{html.escape(team)}</b>?", reply_markup=kb.as_markup(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("live_pts_scored:"))
async def live_pts_scored(cb: CallbackQuery):
    _, mid, side, val, uid = cb.data.split(":")
    mid = int(mid); val = int(val); uid = int(uid)

    m = await _get_match(mid)
    if not m:
        await cb.answer("Матч не найден", show_alert=True); return
    team = m['home'] if side == 'H' else m['away']

    inc = {"points": val}
    if val == 3:
        inc["threes"] = 1

    async with db_lock:
        # 1) обновим индивидуальную статистику
        await _add_stats(m['tid'], m['id'], team, uid, **inc)
        # 2) обновим счёт матча
        await _inc_match_score(mid, side, val)
        # 3) пересчёт агрегатов только по этому игроку
        await recalc_player_stats_for_tournament(m['tid'], user_id=uid)

    # дальше UI (как у тебя): про ассист и т.п.
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="➕ Добавить ассист", callback_data=f"live_pts_ast:{mid}:{side}:{val}:{uid}"))
    kb.row(InlineKeyboardButton(text="✅ Готово (без ассиста)", callback_data=f"match_live:{mid}"))
    await cb.message.edit_text(_render_live_header(await _get_match(mid)) + "\n\nДобавить ассист?", reply_markup=kb.as_markup(), parse_mode="HTML")
    await cb.answer("Записано")


@router.callback_query(F.data.startswith("live_pts_ast:"))
async def live_pts_pick_assist(cb: CallbackQuery):
    _, mid, side, val, scorer_uid = cb.data.split(":")
    mid = int(mid); val = int(val); scorer_uid = int(scorer_uid)
    m = await _get_match(mid)
    if not m: 
        await cb.answer("Матч не найден", show_alert=True); return
    team = m['home'] if side=='H' else m['away']
    roster = await _roster_with_names_live(m['tid'], team)
    roster = [(u,n) for (u,n) in roster if u != scorer_uid]
    if not roster:
        await cb.answer("Некого выбрать", show_alert=True); return
    kb = InlineKeyboardBuilder()
    for uid, name in roster:
        kb.row(InlineKeyboardButton(text=name, callback_data=f"live_pts_ast_sel:{mid}:{side}:{val}:{scorer_uid}:{uid}"))
    kb.row(InlineKeyboardButton(text="🚫 Без ассиста", callback_data=f"match_live:{mid}"))
    await cb.message.edit_text(_render_live_header(m) + "\n\nКто отдал ассист?", reply_markup=kb.as_markup(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("live_pts_ast_sel:"))
async def live_pts_assist_selected(cb: CallbackQuery):
    _, mid, side, val, scorer_uid, ast_uid = cb.data.split(":")
    mid=int(mid); val=int(val); scorer_uid=int(scorer_uid); ast_uid=int(ast_uid)

    m = await _get_match(mid)
    if not m:
        await cb.answer("Матч не найден", show_alert=True); return
    team = m['home'] if side == 'H' else m['away']

    async with db_lock:
        await _add_stats(m['tid'], m['id'], team, ast_uid, assists=1)
        await recalc_player_stats_for_tournament(m['tid'], user_id=ast_uid)

    await cb.message.edit_text(_render_live_header(await _get_match(mid)), reply_markup=_kb_live_root(await _get_match(mid)), parse_mode="HTML")
    await cb.answer("Ассист записан")


# --- single stat events (assist/rebound/steal/block/foul/turnover) with team->player pick ---

@router.callback_query(F.data.startswith("live_evt:"))
async def live_evt_pick_team(cb: CallbackQuery):
    _, mid, stat = cb.data.split(":")
    mid = int(mid)
    m = await _get_match(mid)
    if not m:
        await cb.answer("Матч не найден", show_alert=True); return
    title = {
        "assists":"Ассист", "rebounds":"Подбор", "steals":"Перехват",
        "blocks":"Блок-шот", "fouls":"Фол", "turnovers":"Потеря"
    }.get(stat, stat)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=f"🏠 {m['home']}", callback_data=f"live_evt_team:{mid}:{stat}:H"))
    kb.row(InlineKeyboardButton(text=f"🧳 {m['away']}", callback_data=f"live_evt_team:{mid}:{stat}:A"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"match_live:{mid}"))
    await cb.message.edit_text(_render_live_header(m) + f"\n\n{title}: выбери команду", reply_markup=kb.as_markup(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("live_evt_team:"))
async def live_evt_pick_player(cb: CallbackQuery):
    _, mid, stat, side = cb.data.split(":")
    mid = int(mid)
    m = await _get_match(mid)
    if not m:
        await cb.answer("Матч не найден", show_alert=True); return
    team = m['home'] if side=='H' else m['away']
    roster = await _roster_with_names_live(m['tid'], team)
    if not roster:
        await cb.answer("Состав команды пуст", show_alert=True); return
    kb = InlineKeyboardBuilder()
    for uid, name in roster:
        kb.row(InlineKeyboardButton(text=name, callback_data=f"live_evt_apply:{mid}:{stat}:{side}:{uid}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"live_evt:{mid}:{stat}"))
    await cb.message.edit_text(_render_live_header(m) + f"\n\n{stat}: выбери игрока", reply_markup=kb.as_markup(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("live_evt_apply:"))
async def live_evt_apply(cb: CallbackQuery):
    _, mid, stat, side, uid = cb.data.split(":")
    mid = int(mid); uid = int(uid)

    m = await _get_match(mid)
    if not m:
        await cb.answer("Матч не найден", show_alert=True); return
    team = m['home'] if side == 'H' else m['away']

    async with db_lock:
        await _add_stats(m['tid'], m['id'], team, uid, **{stat: 1})
        await recalc_player_stats_for_tournament(m['tid'], user_id=uid)

    await cb.message.edit_text(_render_live_header(await _get_match(mid)), reply_markup=_kb_live_root(await _get_match(mid)), parse_mode="HTML")
    await cb.answer("Записано")

# --- finish match ---

@router.callback_query(F.data.startswith("live_finish:"))
async def live_finish(cb: CallbackQuery):
    mid = int(cb.data.split(":")[1])
    m = await _get_match(mid)
    if not m:
        await cb.answer("Матч не найден", show_alert=True); return

    async with db_lock:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("PRAGMA busy_timeout=5000;")
            await db.execute("UPDATE matches_simple SET status='finished' WHERE id=?", (mid,))
            await db.commit()
        # после закрытия матча можно пересчитать всем участникам
        await recalc_player_stats_for_tournament(m['tid'], user_id=None)

    await cb.message.edit_text(_render_live_header(await _get_match(mid)) + "\n\n<b>Матч завершён.</b>", parse_mode="HTML", reply_markup=_kb_live_root(await _get_match(mid)))
    await cb.answer("Матч закрыт")


@router.callback_query(F.data == "admin_suggestions")
async def admin_suggestions(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMINS:
        await callback.message.answer("⛔️ Нет доступа.", reply_markup=kb_global(user_id))
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, user_id, text, created_at FROM suggestions "
            "WHERE status='new' ORDER BY datetime(created_at) DESC LIMIT 10"
        )
        rows = await cur.fetchall()

    if not rows:
        await callback.message.answer("📭 Новых идей/репортов нет.", reply_markup=admin_menu_markup())
        return

    # Показываем по одному сообщению на идею, чтобы у каждой были свои кнопки
    for s_id, uid, text, created in rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✉️ Ответить", callback_data=f"suggest_reply:{s_id}:{uid}"),
            InlineKeyboardButton(text="✅ Готово",   callback_data=f"suggest_done:{s_id}")
        ]])
        # тримминг длинных текстов для удобства превью
        preview = text if len(text) <= 900 else (text[:900] + "…")
        await callback.message.answer(
            f"🆕 <b>Идея/репорт №{s_id}</b>\n"
            f"От: <code>{uid}</code>\n"
            f"Когда: <code>{created}</code>\n\n"
            f"{preview}",
            reply_markup=kb
        )

@router.callback_query(F.data.startswith("suggest_done:"))
async def suggest_done(callback: CallbackQuery):
    if callback.from_user.id not in ADMINS:
        await callback.message.answer("⛔️ Нет доступа.")
        return

    try:
        s_id = int(callback.data.split(":")[1])
    except Exception:
        await callback.message.answer("⚠️ Неверные данные.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE suggestions SET status='done' WHERE id=?", (s_id,))
        await db.commit()

    await callback.message.answer(f"✅ Идея №{s_id} отмечена как выполненная.", reply_markup=admin_menu_markup())


@router.callback_query(F.data.startswith("suggest_reply:"))
async def suggest_reply_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS:
        await callback.message.answer("⛔️ Нет доступа.")
        return

    try:
        _, s_id, uid = callback.data.split(":")
        s_id = int(s_id); uid = int(uid)
    except Exception:
        await callback.message.answer("⚠️ Неверные данные.")
        return

    # Сохраняем цель ответа в FSM
    await state.update_data(reply_target_user_id=uid, reply_suggestion_id=s_id)
    await state.set_state(AdminReplyForm.waiting_text)
    await callback.message.answer(
        f"✍️ Напиши ответ пользователю <code>{uid}</code> по идее №{s_id} одним сообщением.\n"
        "Напиши <code>отмена</code>, чтобы выйти."
    )


@router.message(AdminReplyForm.waiting_text)
async def suggest_reply_send(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() == "отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_menu_markup())
        return

    data = await state.get_data()
    uid = data.get("reply_target_user_id")
    s_id = data.get("reply_suggestion_id")
    text = message.html_text or message.text

    if not uid or not s_id or not text:
        await message.answer("⚠️ Не хватает данных для ответа.")
        return

    # Отправляем ответ пользователю
    try:
        await bot.send_message(
            chat_id=uid,
            text=f"✉️ <b>Ответ админа по твоей идее №{s_id}:</b>\n\n{text}"
        )
    except Exception as e:
        logging.warning(f"Ответ пользователю {uid} не отправлен: {e}")
        await message.answer("⚠️ Не удалось отправить пользователю.", reply_markup=admin_menu_markup())
        await state.clear()
        return

    # Помечаем идею как 'answered'
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE suggestions SET status='answered' WHERE id=?", (s_id,))
        await db.commit()

    await message.answer(f"✅ Ответ по идее №{s_id} отправлен пользователю <code>{uid}</code>.", reply_markup=admin_menu_markup())
    await state.clear()


@router.callback_query(F.data == "admin_back_to_menu")
async def admin_back(callback: CallbackQuery):
    await admin_panel(callback)

# --- Удаление команд ---
@router.callback_query(F.data == "admin_delete_teams")
async def admin_delete_teams(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMINS:
        await callback.message.answer("⛔️ Нет доступа.", reply_markup=kb_global(user_id))
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT DISTINCT team_name FROM teams")
        teams = await cursor.fetchall()
        if not teams:
            await callback.message.answer("📭 Нет команд.", reply_markup=admin_menu_markup())
            return
        buttons = []
        for row in teams:
            team = row[0]
            buttons.append([InlineKeyboardButton(text=f"🗑 {team}", callback_data=f"delete_team:{team}")])
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")])
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("<b>🗑 Удаление команд</b>\nНажми на нужную:", reply_markup=markup)

@router.callback_query(F.data.startswith("delete_team:"))
async def delete_team(callback: CallbackQuery):
    team_name = callback.data.split(":")[1]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM teams WHERE team_name = ?", (team_name,))
        await db.execute("UPDATE users SET team = NULL WHERE team = ?", (team_name,))
        await db.commit()
    await callback.message.answer(f"❌ Команда <b>{team_name}</b> удалена.", reply_markup=admin_menu_markup())

@router.callback_query(F.data.startswith("admin_tt_team:"))
async def admin_tt_team_menu(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    _, tid, name = cb.data.split(":", 2)
    tid = int(tid)
    paid = tt_get_paid(tid, name)
    status = "✅ Оплачено" if paid else "❌ Не оплачено"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Переключить оплату", callback_data=f"admin_tt_toggle:{tid}:{name}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_tt:{tid}")]
    ])
    await cb.message.edit_text(f"Команда: {name}\nСтатус оплаты: {status}", reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data.startswith("admin_tt_toggle:"))
async def admin_tt_toggle(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    _, tid, name = cb.data.split(":", 2)
    tid = int(tid)
    new_val = tt_toggle_paid(tid, name)
    status = "✅ Оплачено" if new_val==1 else "❌ Не оплачено"
    await cb.message.edit_text(f"Команда: {name}\nСтатус оплаты: {status}",
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                   [InlineKeyboardButton(text="💰 Переключить оплату", callback_data=f"admin_tt_toggle:{tid}:{name}")],
                                   [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_tt:{tid}")]
                               ]))
    await cb.answer("Статус обновлён")


# --- Рассылка ---
@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS:
        await callback.message.answer("⛔️ Нет доступа.", reply_markup= kb_global(callback.from_user.id))
        return
    await callback.message.answer("📢 Отправь текст рассылки одним сообщением.\n\n<b>Подсказки:</b> можно использовать разметку HTML.\nНапиши <code>отмена</code>, чтобы вернуться.")
    await state.set_state(AdminForm.waiting_broadcast_text)

def kb_admin_tinfo_sections(tid:int):
    rows = [[InlineKeyboardButton(text=title, callback_data=f"admin_tinfo_edit:{tid}:{key}")]
            for key,title in SECTIONS]
    rows.append([InlineKeyboardButton(text="⬅️ К турниру", callback_data=f"admin_tournament:{tid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@router.callback_query(F.data.startswith("admin_tinfo:"))
async def admin_tinfo(cb: CallbackQuery):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    tid = int(cb.data.split(":")[1])
    await cb.message.edit_text("Какой раздел редактируем?", reply_markup=kb_admin_tinfo_sections(tid))
    await cb.answer()

@router.callback_query(F.data.startswith("admin_tinfo_edit:"))
async def admin_tinfo_edit(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMINS:
        await cb.answer("Нет доступа", show_alert=True); return
    _, tid, key = cb.data.split(":")
    tid = int(tid)
    await state.update_data(_tinfo_tid=tid, _tinfo_key=key)
    with db() as con:
        row = con.execute("SELECT content FROM tournament_info WHERE tournament_id=? AND section=?",
                          (tid, key)).fetchone()
    current = row[0] if row and row[0] else ""
    prompt = f"Введи новый текст раздела <b>{dict(SECTIONS).get(key,key)}</b>.\n\nТекущий:\n{current or '—'}"
    await cb.message.answer(prompt)
    await state.set_state(AdminForm.waiting_tinfo_section_text)
    await cb.answer()

@router.message(AdminForm.waiting_tinfo_section_text)
async def admin_tinfo_save(message: Message, state: FSMContext):
    data = await state.get_data()
    tid, key = data.get("_tinfo_tid"), data.get("_tinfo_key")
    text = message.html_text or message.text or ""
    with db() as con:
        con.execute(
            "INSERT INTO tournament_info(tournament_id, section, content, updated_at) "
            "VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(tournament_id, section) DO UPDATE SET content=excluded.content, updated_at=CURRENT_TIMESTAMP",
            (tid, key, text)
        )
        con.commit()
    await state.clear()
    await message.answer("✅ Сохранено.", reply_markup=kb_admin_tinfo_sections(tid))

@router.message(AdminForm.waiting_broadcast_text)
async def admin_broadcast_collect(message: Message, state: FSMContext):
    if message.text and message.text.lower().strip() == "отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_menu_markup())
        return
    text = message.html_text or message.text
    recipients = await get_all_recipients()
    sent = 0
    failed = 0
    for uid in recipients:
        try:
            await bot.send_message(uid, text)
            sent += 1
        except Exception as e:
            failed += 1
            logging.warning(f"Broadcast to {uid} failed: {e}")
    await state.clear()
    await message.answer(f"✅ Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}", reply_markup=admin_menu_markup())

# --- Опрос ---
@router.callback_query(F.data == "admin_poll")
async def admin_poll_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS:
        await callback.message.answer("⛔️ Нет доступа.", reply_markup= kb_global(callback.from_user.id))
        return
    await callback.message.answer("📊 Отправь текст вопроса для опроса.\nНапиши <code>отмена</code>, чтобы вернуться.")
    await state.set_state(AdminForm.waiting_poll_question)




@router.message(AdminForm.waiting_poll_options)
async def admin_poll_options(message: Message, state: FSMContext):
    if message.text and message.text.lower().strip() == "отмена":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_menu_markup())
        return

    options = [opt.strip() for opt in (message.text or "").split("\n") if opt.strip()]
    if len(options) < 2 or len(options) > 10:
        await message.answer("⚠️ Нужны от 2 до 10 вариантов. Пришли заново, каждый с новой строки.")
        return

    data = await state.get_data()
    question = data.get("poll_question", "Опрос")

    # 1) регистрируем «группу» рассылки опросов
    group_id = str(uuid.uuid4())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO polls_group (group_id, question, options) VALUES (?, ?, ?)",
            (group_id, question, json.dumps(options))
        )
        await db.commit()

    # 2) рассылаем и сохраняем каждый poll
    recipients = await get_all_recipients()
    sent = failed = 0
    for uid in recipients:
        try:
            msg = await bot.send_poll(
                chat_id=uid,
                question=question,
                options=options,
                is_anonymous=False,                 # ← ДОЛЖНО БЫТЬ False, чтобы видеть кто проголосовал
                allows_multiple_answers=False
            )
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "INSERT INTO polls (poll_id, group_id, question, options, chat_id, message_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (msg.poll.id, group_id, question, json.dumps(options), uid, msg.message_id)
                )
                await db.commit()
            sent += 1
        except Exception as e:
            failed += 1
            logging.warning(f"Poll to {uid} failed: {e}")

    await state.clear()
    await message.answer(f"✅ Опрос отправлен.\nОтправлено: {sent}\nОшибок: {failed}", reply_markup=admin_menu_markup())

@router.poll_answer()
async def on_poll_answer(poll_answer: PollAnswer):
    poll_id = poll_answer.poll_id
    user_id = poll_answer.user.id
    option_id = poll_answer.option_ids[0] if poll_answer.option_ids else -1
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO poll_votes (poll_id, user_id, option_id) VALUES (?, ?, ?)",
            (poll_id, user_id, option_id)
        )
        await db.commit()


@router.callback_query(F.data == "admin_poll_results")
async def admin_poll_results(callback: CallbackQuery):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # берём последний опрос
            cur = await db.execute(
                "SELECT group_id, question, options FROM polls_group "
                "ORDER BY datetime(created_at) DESC LIMIT 1"
            )
            row = await cur.fetchone()
            if not row:
                await callback.message.answer("❌ Нет опросов", reply_markup=admin_menu_markup())
                return

            group_id, question, options_json = row
            options = json.loads(options_json)

            # все poll_id этой рассылки
            cur = await db.execute("SELECT poll_id FROM polls WHERE group_id=?", (group_id,))
            poll_ids = [r[0] for r in await cur.fetchall()]
            if not poll_ids:
                await callback.message.answer("❌ По этому опросу ещё нет данных", reply_markup=admin_menu_markup())
                return

            # читаем голоса
            placeholders = ",".join("?" for _ in poll_ids)
            cur = await db.execute(
                f"SELECT poll_id, user_id, option_id "
                f"FROM poll_votes WHERE poll_id IN ({placeholders})",
                poll_ids
            )
            rows = await cur.fetchall()

            # кэш имён
            names_cache = {}
            async def get_name(uid: int) -> str:
                if uid in names_cache:
                    return names_cache[uid]
                # сначала ищем в users
                c1 = await db.execute("SELECT full_name FROM users WHERE user_id=?", (uid,))
                r1 = await c1.fetchone()
                if r1 and r1[0]:
                    names_cache[uid] = r1[0]
                    return r1[0]
                # иначе в free_agents
                c2 = await db.execute("SELECT name FROM free_agents WHERE user_id=?", (uid,))
                r2 = await c2.fetchone()
                if r2 and r2[0]:
                    names_cache[uid] = r2[0]
                    return r2[0]
                # запасной вариант
                names_cache[uid] = f"id{uid}"
                return names_cache[uid]

            # агрегируем
            counts = [0] * len(options)
            voters_by_option = {i: [] for i in range(len(options))}
            for _poll_id, uid, opt in rows:
                if 0 <= opt < len(options):
                    counts[opt] += 1
                    voters_by_option[opt].append(uid)

            # СБОР ТЕКСТА — тоже внутри with db, потому что get_name использует БД
            total = sum(counts)
            lines = [
                "📈 Результаты опроса:",
                f"<b>{question}</b>",
                f"\n<b>Всего голосов:</b> {total}\n"
            ]
            for i, opt_text in enumerate(options):
                voters = voters_by_option[i]
                # показываем до 25 имён
                names = [await get_name(u) for u in voters[:25]]
                extra = f" и ещё {len(voters) - 25}…" if len(voters) > 25 else ""
                names_str = ", ".join(names) if names else "—"
                lines.append(f"{i+1}. {opt_text} — {counts[i]}\n    {names_str}{extra}\n")

            text = "\n".join(lines)

        # отправляем уже после выхода из 'with' (соединение закрыто, но текст готов)
        await callback.message.answer(text, reply_markup=admin_menu_markup())

    except Exception as e:
        logging.exception("admin_poll_results failed")
        await callback.message.answer("⚠️ Ошибка при формировании результатов. Проверь логи.", reply_markup=admin_menu_markup())

@router.callback_query(F.data == "admin_poll_close")
async def admin_poll_close(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMINS:
        await callback.message.answer("⛔️ Нет доступа.", reply_markup= kb_global(user_id))
        return

    # 1) Находим последний НЕ закрытый опрос
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT group_id FROM polls_group WHERE is_closed=0 "
            "ORDER BY datetime(created_at) DESC LIMIT 1"
        )
        row = await cur.fetchone()

    if not row:
        await callback.message.answer("❌ Открытых опросов нет.", reply_markup=admin_menu_markup())
        return

    group_id = row[0]

    # 2) Забираем все сообщения с опросами этой группы
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT chat_id, message_id FROM polls WHERE group_id=?",
            (group_id,)
        )
        polls_to_close = await cur.fetchall()

    if not polls_to_close:
        await callback.message.answer("❌ Не найдено сообщений с опросами для этой группы.", reply_markup=admin_menu_markup())
        return

    # 3) Закрываем каждый опрос
    closed, failed = 0, 0
    for chat_id, message_id in polls_to_close:
        try:
            await bot.stop_poll(chat_id=chat_id, message_id=message_id)
            closed += 1
        except Exception as e:
            failed += 1
            logging.warning(f"stop_poll failed for chat_id={chat_id}, message_id={message_id}: {e}")

    # 4) Помечаем группу как закрытую
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE polls_group SET is_closed=1 WHERE group_id=?", (group_id,))
        await db.commit()

    await callback.message.answer(
        f"✅ Опрос закрыт.\nЗакрыто: {closed}\nОшибок: {failed}",
        reply_markup=admin_menu_markup()
    )




if __name__ == "__main__":
    asyncio.run(main())
