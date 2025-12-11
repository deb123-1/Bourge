import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ==========================
# CONFIG
# ==========================
TOKEN = "8435928130:AAGDT7luPVTmKYeimEVlqlG5uaO--B6G6Rk"
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ==========================
# БАЗА ДАННЫХ
# ==========================
db = sqlite3.connect("bot.db")
cursor = db.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    messages INTEGER DEFAULT 0,
    warns INTEGER DEFAULT 0,
    mutes INTEGER DEFAULT 0,
    bans INTEGER DEFAULT 0,
    role TEXT DEFAULT 'user'
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS tasks(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_id INTEGER,
    text TEXT,
    status TEXT DEFAULT 'active'
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS triggers(
    trigger TEXT,
    response TEXT
)""")

db.commit()


# ==========================
# ФУНКЦИИ РАБОТЫ С БД
# ==========================
def add_user(uid):
    cursor.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    db.commit()

def add_message(uid):
    cursor.execute("UPDATE users SET messages = messages + 1 WHERE user_id = ?", (uid,))
    db.commit()

def set_role(uid, role):
    cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, uid))
    db.commit()

def get_role(uid):
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (uid,))
    row = cursor.fetchone()
    return row[0] if row else "user"

def warn_user(uid):
    cursor.execute("UPDATE users SET warns = warns + 1 WHERE user_id = ?", (uid,))
    db.commit()

def mute_user(uid):
    cursor.execute("UPDATE users SET mutes = mutes + 1 WHERE user_id = ?", (uid,))
    db.commit()

def ban_user(uid):
    cursor.execute("UPDATE users SET bans = bans + 1 WHERE user_id = ?", (uid,))
    db.commit()


# ==========================
# КНОПКИ
# ==========================
def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📌 Задачи", callback_data="tasks")
    kb.button(text="⚠️ Наказания", callback_data="punish")
    kb.button(text="📊 Аналитика", callback_data="stats")
    kb.button(text="🤖 Автоответы", callback_data="triggers")
    kb.adjust(2)
    return kb.as_markup()


# ==========================
# СТАРТ
# ==========================
@dp.message(Command("start"))
async def start_cmd(msg: Message):
    add_user(msg.from_user.id)
    await msg.answer("Йо, я тут, готов рулить чатом 😎", reply_markup=main_menu())


# ==========================
# СТАТИСТИКА
# ==========================
@dp.callback_query(F.data == "stats")
async def show_stats(cb: CallbackQuery):
    uid = cb.from_user.id
    cursor.execute("SELECT messages, warns, mutes, bans, role FROM users WHERE user_id = ?", (uid,))
    m, w, mute, b, r = cursor.fetchone()

    await cb.message.edit_text(
        f"📊 *Твоя аналитика:* \n"
        f"Сообщений: **{m}**\n"
        f"Предупреждений: **{w}**\n"
        f"Mute: **{mute}**\n"
        f"Ban: **{b}**\n"
        f"Роль: **{r}**",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )


# ==========================
# ЗАДАЧИ
# ==========================
@dp.callback_query(F.data == "tasks")
async def tasks_menu(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить", callback_data="task_add")
    kb.button(text="📋 Список", callback_data="task_list")
    kb.adjust(2)
    await cb.message.edit_text("Управление задачами:", reply_markup=kb.as_markup())


# Добавление задачи
@dp.callback_query(F.data == "task_add")
async def wait_task_text(cb: CallbackQuery):
    await cb.message.edit_text("Отправь текст задачи:")

    @dp.message()
    async def add_task(msg: Message):
        cursor.execute("INSERT INTO tasks (creator_id, text) VALUES (?,?)",
                       (msg.from_user.id, msg.text))
        db.commit()
        await msg.answer("Готово, задача добавлена ✔️")
        dp.message.handlers.pop()


# Список задач
@dp.callback_query(F.data == "task_list")
async def show_task_list(cb: CallbackQuery):
    cursor.execute("SELECT id, text, status FROM tasks WHERE status='active'")
    rows = cursor.fetchall()
    if not rows:
        await cb.message.edit_text("Список пуст.", reply_markup=main_menu())
        return

    text = "📌 *Активные задачи:*\n\n"
    for tid, t, s in rows:
        text += f"• `{tid}` — {t}\n"

    await cb.message.edit_text(text, reply_markup=main_menu(), parse_mode="Markdown")


# ==========================
# НАКАЗАНИЯ
# ==========================
@dp.callback_query(F.data == "punish")
async def punish_menu(cb: CallbackQuery):
    await cb.message.edit_text(
        "Выбери наказание:\n/mute ID\n/warn ID\n/ban ID",
        reply_markup=main_menu()
    )


@dp.message(Command("warn"))
async def warn_cmd(msg: Message):
    if len(msg.text.split()) < 2:
        return await msg.answer("Укажи ID: /warn 123")

    uid = int(msg.text.split()[1])
    warn_user(uid)
    await msg.answer(f"Пользователь {uid} получил warn 🔥")


@dp.message(Command("mute"))
async def mute_cmd(msg: Message):
    if len(msg.text.split()) < 2:
        return await msg.answer("Укажи ID: /mute 123")

    uid = int(msg.text.split()[1])
    mute_user(uid)
    await msg.answer(f"{uid} в муте 😶")


@dp.message(Command("ban"))
async def ban_cmd(msg: Message):
    if len(msg.text.split()) < 2:
        return await msg.answer("Укажи ID: /ban 123")

    uid = int(msg.text.split()[1])
    ban_user(uid)
    await msg.answer(f"{uid} забанен 🚫")


# ==========================
# ТРИГГЕРЫ / АВТООТВЕТЫ
# ==========================
@dp.callback_query(F.data == "triggers")
async def trig_menu(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить триггер", callback_data="tr_add")
    kb.button(text="📃 Список", callback_data="tr_list")
    kb.adjust(1)
    await cb.message.edit_text("Управление автоответами:", reply_markup=kb.as_markup())


@dp.callback_query(F.data == "tr_add")
async def trig_add_wait(cb: CallbackQuery):
    await cb.message.edit_text("Напиши триггер в формате:\n`триггер | ответ`", parse_mode="Markdown")

    @dp.message()
    async def save_trigger(msg: Message):
        if "|" not in msg.text:
            return await msg.answer("Формат: `привет | и тебе хай`")

        t, r = msg.text.split("|", 1)
        cursor.execute("INSERT INTO triggers (trigger, response) VALUES (?,?)",
                       (t.strip().lower(), r.strip()))
        db.commit()

        await msg.answer("Готово 🔥 Триггер сохранён.")
        dp.message.handlers.pop()


@dp.callback_query(F.data == "tr_list")
async def trig_list(cb: CallbackQuery):
    cursor.execute("SELECT trigger, response FROM triggers")
    rows = cursor.fetchall()
    if not rows:
        return await cb.message.edit_text("Нет триггеров.", reply_markup=main_menu())

    text = "🤖 *Триггеры:*\n\n"
    for t, r in rows:
        text += f"• `{t}` → {r}\n"

    await cb.message.edit_text(text, reply_markup=main_menu(), parse_mode="Markdown")


# ==========================
# ОБРАБОТЧИК СООБЩЕНИЙ (статистика + триггеры)
# ==========================
@dp.message()
async def msg_handler(msg: Message):
    uid = msg.from_user.id
    add_user(uid)
    add_message(uid)

    text = msg.text.lower()

    cursor.execute("SELECT response FROM triggers WHERE trigger = ?", (text,))
    row = cursor.fetchone()
    if row:
        await msg.answer(row[0])


# ==========================
# RUN
# ==========================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
