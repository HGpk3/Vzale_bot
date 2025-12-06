import asyncio
import os
import logging
import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "tournament.db"
ADMINS = [409436763, 469460286]

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

class Form(StatesGroup):
    waiting_for_name = State()
    waiting_for_team_status = State()
    waiting_for_team_name = State()
    waiting_for_team_selection = State()
    waiting_for_free_info = State()

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
        kb.row(InlineKeyboardButton(text="🚪 Выйти из команды", callback_data="leave_team"))
    else:
        kb.row(InlineKeyboardButton(text="🔄 Присоединиться к команде", callback_data="rejoin_team"))

    

    if is_free_agent:
        kb.row(InlineKeyboardButton(text="🚫 Удалить анкету свободного игрока", callback_data="leave_free_agents"))


    if user_id in ADMINS:
        kb.row(InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_panel"))
        kb.row(InlineKeyboardButton(text="🧍 Свободные игроки", callback_data="free_agents"))
        kb.row(InlineKeyboardButton(text="📋 Список команд", callback_data="list_teams"))
    
    kb.row(InlineKeyboardButton(text="🗑 Удалить профиль", callback_data="delete_profile"))
    return kb.as_markup()

@router.message(F.text == "/start")
async def start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if await user_exists(user_id):
        menu = await get_main_menu(user_id)
        await message.answer("✅ Ты уже зарегистрирован!\nВыбери действие:", reply_markup=menu)
        return
    await message.answer("👋 Привет, мы Vzale! Дата первого турнира 24 августа.\n\nМесто проведения:\nСПб, Вознесенский проспект 44-46\n\n Личный взнос 300руб. уже на корте\n\n Давай начнём регистрацию.\n\n✍️ Напиши свои ФИО:")
    await state.set_state(Form.waiting_for_name)

@router.message(Form.waiting_for_name)
async def enter_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, я в команде(уже есть зарегистриванная команда)", callback_data="has_team")],
        [InlineKeyboardButton(text="🆕 Хочу зарегистрировать команду", callback_data="new_team")],
        [InlineKeyboardButton(text="🧍 Я свободный игрок(тебя могут взять другие команды)", callback_data="free_agent")]
    ])
    await message.answer("🤔 Ты уже в команде или хочешь создать новую?\n\nВыбери вариант ниже:", reply_markup=markup)
    await state.set_state(Form.waiting_for_team_status)

@router.callback_query(Form.waiting_for_team_status)
async def choose_status(callback: CallbackQuery, state: FSMContext):
    if callback.data == "has_team":
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT DISTINCT team_name FROM teams")
            rows = await cursor.fetchall()
            if rows:
                buttons = [[InlineKeyboardButton(text=row[0], callback_data=f"join_team:{row[0]}")] for row in rows]
                await callback.message.answer("📌 Выбери команду из списка:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
                await state.set_state(Form.waiting_for_team_selection)
            else:
                await callback.message.answer("🚫 Пока нет зарегистрированных команд.", reply_markup=await get_main_menu(callback.from_user.id))
    elif callback.data == "new_team":
        await callback.message.answer("🆕 Введи название своей команды:")
        await state.set_state(Form.waiting_for_team_name)
    elif callback.data == "free_agent":
        await callback.message.answer("📝 Напиши о себе:\n\n<em>Амплуа, возраст, рост, уровень игры</em>")
        await state.set_state(Form.waiting_for_free_info)

@router.message(Form.waiting_for_team_name)
async def register_new_team(message: Message, state: FSMContext):
    data = await state.get_data()
    team_name = message.text.strip()
    user_id = message.from_user.id
    full_name = data["full_name"]
    async with aiosqlite.connect(DB_PATH) as db:
        if await user_exists(user_id):
            await message.answer("⚠️ Ты уже зарегистрирован.", reply_markup=await get_main_menu(user_id))
            return
        await db.execute("INSERT INTO users (user_id, full_name, team) VALUES (?, ?, ?)", (user_id, full_name, team_name))
        await db.execute("INSERT INTO teams (team_name, member_id, member_name) VALUES (?, ?, ?)", (team_name, user_id, full_name))
        await db.commit()
    await notify_admins(f"🆕 <b>Новая команда зарегистрирована:</b>\n<b>{team_name}</b>\n👤 {full_name}")
    await message.answer(f"🎉 Команда <b>{team_name}</b> успешно создана! \n\nПодпишись чтобы ничего не пропустить:\n https://t.me/vzzale \n https://vk.com/vzale1 \n https://www.instagram.com/vzale_bb?igsh=Y2Y1Nmx5YTE4aWJp", reply_markup=await get_main_menu(user_id))
    await state.clear()

@router.callback_query(Form.waiting_for_team_selection, F.data.startswith("join_team"))
async def join_team(callback: CallbackQuery, state: FSMContext):
    team_name = callback.data.split(":")[1]
    user_id = callback.from_user.id
    data = await state.get_data()
    full_name = data.get("full_name", "Игрок")
    async with aiosqlite.connect(DB_PATH) as db:
        if await user_exists(user_id):
            await callback.message.answer("⚠️ Ты уже зарегистрирован.", reply_markup=await get_main_menu(user_id))
            return
        await db.execute("INSERT INTO users (user_id, full_name, team) VALUES (?, ?, ?)", (user_id, full_name, team_name))
        await db.execute("INSERT INTO teams (team_name, member_id, member_name) VALUES (?, ?, ?)", (team_name, user_id, full_name))
        await db.commit()
    await notify_admins(f"👤 <b>Новый игрок присоединился к команде:</b>\n<b>{team_name}</b>\n🧍 {full_name}")
    await callback.message.answer(f"✅ Ты добавлен в команду <b>{team_name}</b>!\n\nПодпишись чтобы ничего не пропустить:\n https://t.me/vzzale \n https://vk.com/vzale1 \n https://www.instagram.com/vzale_bb?igsh=Y2Y1Nmx5YTE4aWJp", reply_markup=await get_main_menu(user_id))
    await state.clear()

@router.callback_query(F.data == "leave_free_agents")
async def leave_free_agents(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM free_agents WHERE user_id = ?", (user_id,))
        await db.commit()

    await callback.message.answer("✅ Твоя анкета свободного игрока удалена.(Если хочешь добавиться в команду, то введи /start)", reply_markup=await get_main_menu(user_id))


@router.callback_query(F.data == "my_team")
async def show_my_team(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT team FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            await callback.message.answer("🚫 Ты пока не в команде.", reply_markup=await get_main_menu(user_id))
            return
        team_name = row[0]
        cursor = await db.execute("SELECT member_name FROM teams WHERE team_name = ?", (team_name,))
        members = await cursor.fetchall()
        names = "\n".join([f"• {m[0]}" for m in members])
        await callback.message.answer(f"<b>🏀 Твоя команда: {team_name}</b>\n\n👥 Участники:\n{names}", reply_markup=await get_main_menu(user_id))

@router.callback_query(F.data == "list_teams")
async def show_teams(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT DISTINCT team_name FROM teams")
        teams = await cursor.fetchall()
        if not teams:
            await callback.message.answer("🚫 Пока нет зарегистрированных команд.", reply_markup=await get_main_menu(callback.from_user.id))
            return
        text = "<b>📒 Список команд:</b>\n\n"
        for row in teams:
            team = row[0]
            cursor = await db.execute("SELECT member_name FROM teams WHERE team_name = ?", (team,))
            members = await cursor.fetchall()
            members_text = "\n ".join([m[0] for m in members])
           
            text += f"🏷 <b>{team}</b>:\n {members_text}\n"
        await callback.message.answer(text, reply_markup=await get_main_menu(callback.from_user.id))

@router.callback_query(F.data == "free_agents")
async def show_free_agents(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMINS:
        await callback.message.answer("⛔️ Доступ запрещён.", reply_markup=await get_main_menu(user_id))
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT name, info FROM free_agents")
        agents = await cursor.fetchall()
        if not agents:
            await callback.message.answer("📭 Список свободных игроков пуст.", reply_markup=await get_main_menu(user_id))
            return
        text = "<b>🧍 Свободные игроки:</b>\n\n"
        for name, info in agents:
            text += f"• <b>{name}</b>\n{info}\n\n"
        await callback.message.answer(text, reply_markup=await get_main_menu(user_id))

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


    await message.answer("🧍 Ты добавлен в список свободных игроков!", reply_markup=await get_main_menu(message.from_user.id))
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

    await callback.message.answer(
        "🗑 Твой профиль был удалён. Чтобы пройти регистрацию заново — введи /start"
    )

@router.callback_query(F.data == "leave_team")
async def leave_team(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        # Получаем команду пользователя
        cursor = await db.execute("SELECT team FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()

        if not row or not row[0]:
            await callback.message.answer("❌ Ты не состоишь ни в одной команде.", reply_markup=await get_main_menu(user_id))
            return

        team = row[0]

        # Удаляем пользователя из команды
        await db.execute("UPDATE users SET team = NULL WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM teams WHERE member_id = ?", (user_id,))
        await db.commit()

    await callback.message.answer(f"🚪 Ты вышел из команды <b>{team}</b>.", reply_markup=await get_main_menu(user_id))

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

    await callback.message.answer(
        "🔁 Ты хочешь снова присоединиться?\n\nВыбери один из вариантов:",
        reply_markup=markup
    )

    await state.set_state(Form.waiting_for_team_status)


@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ADMINS:
        await callback.message.answer("⛔️ Нет доступа.", reply_markup=await get_main_menu(user_id))
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT DISTINCT team_name FROM teams")
        teams = await cursor.fetchall()
        if not teams:
            await callback.message.answer("📭 Нет команд.", reply_markup=await get_main_menu(user_id))
            return
        buttons = []
        for row in teams:
            team = row[0]
            buttons.append([
                InlineKeyboardButton(text=f"🗑 {team}", callback_data=f"delete_team:{team}")
            ])
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer("<b>🛠 Удаление команд</b>\nНажми на нужную:", reply_markup=markup)

@router.callback_query(F.data.startswith("delete_team:"))
async def delete_team(callback: CallbackQuery):
    team_name = callback.data.split(":")[1]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM teams WHERE team_name = ?", (team_name,))
        await db.execute("UPDATE users SET team = NULL WHERE team = ?", (team_name,))
        await db.commit()
    await callback.message.answer(f"❌ Команда <b>{team_name}</b> удалена.", reply_markup=await get_main_menu(callback.from_user.id))
    await admin_panel(callback)

    @router.callback_query(F.data == "admin_poll_results")
async def admin_poll_results(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT group_id, question, options FROM polls_group ORDER BY created_at DESC LIMIT 1")
        row = await cur.fetchone()
        if not row:
            await callback.message.answer("❌ Нет опросов")
            return

        group_id, question, options_json = row
        options = json.loads(options_json)

        # Все poll_id этой группы
        cur = await db.execute("SELECT poll_id FROM polls WHERE group_id=?", (group_id,))
        poll_ids = [r[0] for r in await cur.fetchall()]
        if not poll_ids:
            await callback.message.answer("❌ Опросов нет")
            return

        # Все голоса
        placeholders = ",".join("?" * len(poll_ids))
        cur = await db.execute(
            f"SELECT user_id, option_id FROM poll_votes WHERE poll_id IN ({placeholders})",
            poll_ids
        )
        votes = await cur.fetchall()

        # Подтянем имена
        async def get_name(uid):
            c1 = await db.execute("SELECT full_name FROM users WHERE user_id=?", (uid,))
            r1 = await c1.fetchone()
            if r1 and r1[0]:
                return r1[0]
            c2 = await db.execute("SELECT name FROM free_agents WHERE user_id=?", (uid,))
            r2 = await c2.fetchone()
            if r2 and r2[0]:
                return r2[0]
            return f"id{uid}"

        # Считаем
        results = {i: [] for i in range(len(options))}
        for uid, opt in votes:
            if 0 <= opt < len(options):
                results[opt].append(await get_name(uid))

    # Формируем текст
    text = f"📈 Результаты опроса:\n\n<b>{question}</b>\n\n"
    for i, opt in enumerate(options):
        voters = results[i]
        names_str = ", ".join(voters) if voters else "—"
        text += f"{i+1}. {opt} — {len(voters)} голосов\n    {names_str}\n\n"

    await callback.message.answer(text, reply_markup=admin_menu_markup())


async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
