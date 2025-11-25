# ————————————————————————————————————————————
#  TG MODERATION BOT WITH ADMIN LEVELS (v2)
#  pip install python-telegram-bot==20.5 aiosqlite
# ————————————————————————————————————————————

import logging
import asyncio
import aiosqlite
from datetime import datetime, timedelta
from telegram import (
    Update,
    ChatPermissions,
    ChatMember,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ChatMemberHandler,
    MessageHandler,
    filters,
)

# ————— YOUR SETTINGS —————
BOT_TOKEN = "ТОКЕН_СЮДА"
DB_PATH = "iris_bot.db"
MOD_LOG_CHAT = 0  # чат, куда бот скидывает логи (0 = выкл)
WELCOME_TEXT = "Йо, {name}! Добро пожаловать в {chat}. Правила ниже 🔻"

DEFAULT_RULES = """1) Не флудим
2) Не бомбим в чат оскорбами
3) Рекламу — в мусорку
4) Модеры тут — как судьи, их слово финальное
"""

# ————— LEVELS —————
LEVEL_NAMES = {
    1: "Хелпер",
    2: "Модер",
    3: "Старший модер",
    4: "Админ",
    5: "Владелец"
}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("BOT")


# ——————————————————————— DB INIT ———————————————————————
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER,
                user_id INTEGER,
                level INTEGER,
                PRIMARY KEY (chat_id, user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS warns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                mod_id INTEGER,
                reason TEXT,
                time TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                chat_id INTEGER PRIMARY KEY,
                text TEXT
            )
        """)

        await db.commit()


# ——————————————————————— DB HELPERS ———————————————————————
async def get_level(chat_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT level FROM users WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        row = await cur.fetchone()
        return row[0] if row else 0


async def set_level(chat_id, user_id, level):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (chat_id, user_id, level)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id, user_id)
            DO UPDATE SET level=excluded.level
        """, (chat_id, user_id, level))
        await db.commit()


async def add_warn(chat_id, user_id, mod_id, reason):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO warns (chat_id, user_id, mod_id, reason, time) VALUES (?, ?, ?, ?, ?)",
                         (chat_id, user_id, mod_id, reason, datetime.utcnow()))
        await db.commit()


async def get_warns(chat_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT mod_id, reason, time FROM warns WHERE chat_id=? AND user_id=? ORDER BY id ASC",
                               (chat_id, user_id))
        return await cur.fetchall()


async def clear_warns(chat_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        await db.commit()


async def get_rules(chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT text FROM rules WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        return row[0] if row else None


async def set_rules(chat_id, text):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO rules (chat_id, text) VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET text=excluded.text
        """, (chat_id, text))
        await db.commit()


# ——————————————————————— UTILS ———————————————————————
async def log_action(text, context):
    if MOD_LOG_CHAT != 0:
        try:
            await context.bot.send_message(MOD_LOG_CHAT, text)
        except:
            pass


def check_level(level, need):
    return level >= need


async def get_target(update, context):
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    if context.args:
        try:
            uid = int(context.args[0])
            member = await update.effective_chat.get_member(uid)
            return member.user
        except:
            return None
    return None


# ————————————————————— COMMANDS —————————————————————

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Йоу, я мод-бот. Пиши /rules — узнаешь, что к чему 🤙")


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rules = await get_rules(update.effective_chat.id) or DEFAULT_RULES
    await update.message.reply_text("Правила чата:\n\n" + rules)


async def setrules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lvl = await get_level(update.effective_chat.id, update.effective_user.id)
    if not check_level(lvl, 4):
        await update.message.reply_text("Тебе рановато в админку 😭")
        return

    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Напиши новые правила после команды.")
        return

    await set_rules(update.effective_chat.id, text)
    await update.message.reply_text("Правила обновлены.")
    await log_action(f"📝 {update.effective_user.full_name} обновил правила.", context)


async def setlevel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    author_lvl = await get_level(chat.id, user.id)
    if not check_level(author_lvl, 5):
        await update.message.reply_text("Ты не можешь раздавать роли.")
        return

    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Формат: /setlevel <reply> <1-5>")
        return

    target = await get_target(update, context)
    if not target:
        await update.message.reply_text("Юзер не найден.")
        return

    if str(context.args[-1]).isdigit():
        lvl = int(context.args[-1])
    else:
        await update.message.reply_text("Укажи уровень 1-5.")
        return

    if lvl < 1 or lvl > 5:
        await update.message.reply_text("Уровень должен быть 1-5.")
        return

    if target.id == user.id:
        await update.message.reply_text("Нельзя выдавать уровни себе.")
        return

    await set_level(chat.id, target.id, lvl)
    await update.message.reply_text(f"{target.full_name} теперь {LEVEL_NAMES[lvl]} 🔥")
    await log_action(f"⚡ {user.full_name} выставил {LEVEL_NAMES[lvl]} пользователю {target.full_name}", context)


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = await get_target(update, context) or update.effective_user
    lvl = await get_level(update.effective_chat.id, target.id)

    await update.message.reply_text(
        f"👤 {target.full_name}\n"
        f"ID: {target.id}\n"
        f"Роль: {LEVEL_NAMES.get(lvl, 'Гость')}"
    )


# ——————————— WARN ———————————
async def warn(update, context):
    chat = update.effective_chat
    user = update.effective_user
    lvl = await get_level(chat.id, user.id)

    if not check_level(lvl, 2):
        await update.message.reply_text("Тебе нельзя выдавать варны.")
        return

    target = await get_target(update, context)
    if not target:
        await update.message.reply_text("Не нашёл пользователя.")
        return
    
    if await get_level(chat.id, target.id) >= lvl:
        await update.message.reply_text("Нельзя мутить/варнить равного или выше.")
        return

    reason = " ".join(context.args[1:]) if context.args else "Без причины"
    await add_warn(chat.id, target.id, user.id, reason)

    w = await get_warns(chat.id, target.id)
    count = len(w)

    await update.message.reply_text(
        f"⚠ Варн выдан {target.full_name}\nПричина: {reason}\nВсего: {count}"
    )
    await log_action(f"⚠ {user.full_name} выдал варн {target.full_name}. Причина: {reason}", context)


async def warns_list(update, context):
    target = await get_target(update, context) or update.effective_user
    rows = await get_warns(update.effective_chat.id, target.id)

    if not rows:
        await update.message.reply_text("Варнов нет.")
        return

    txt = f"⚠ Варны {target.full_name}:\n\n"
    for w in rows:
        mod_id, reason, time = w
        txt += f"- {reason} (от {mod_id}, время: {time})\n"

    await update.message.reply_text(txt)


async def clearwarns(update, context):
    chat = update.effective_chat
    user = update.effective_user
    lvl = await get_level(chat.id, user.id)

    if not check_level(lvl, 3):
        await update.message.reply_text("Тебе нельзя чистить варны.")
        return

    target = await get_target(update, context)
    if not target:
        return await update.message.reply_text("Не найден.")

    await clear_warns(chat.id, target.id)
    await update.message.reply_text(f"Варны {target.full_name} очищены.")
    await log_action(f"♻ {user.full_name} очистил варны {target.full_name}", context)


# ——————————— MUTE / UNMUTE ———————————
async def mute(update, context):
    chat = update.effective_chat
    user = update.effective_user
    lvl = await get_level(chat.id, user.id)

    if not check_level(lvl, 2):
        return await update.message.reply_text("Недостаточно прав.")

    target = await get_target(update, context)
    if not target:
        return await update.message.reply_text("Не найден.")

    if await get_level(chat.id, target.id) >= lvl:
        return await update.message.reply_text("Нельзя мутить равного/старшего.")

    minutes = int(context.args[-1]) if context.args and context.args[-1].isdigit() else 5
    until = datetime.utcnow() + timedelta(minutes=minutes)

    perms = ChatPermissions(can_send_messages=False)
    await context.bot.restrict_chat_member(chat.id, target.id, perms, until)

    await update.message.reply_text(f"{target.full_name} замьючен на {minutes} минут 🔇")
    await log_action(f"🔇 {user.full_name} замутил {target.full_name} на {minutes} минут", context)


async def unmute(update, context):
    chat = update.effective_chat
    user = update.effective_user
    lvl = await get_level(chat.id, user.id)

    if not check_level(lvl, 3):
        return await update.message.reply_text("Недостаточно прав.")

    target = await get_target(update, context)
    if not target:
        return await update.message.reply_text("Не найден.")

    perms = ChatPermissions(can_send_messages=True)
    await context.bot.restrict_chat_member(chat.id, target.id, perms)
    await update.message.reply_text(f"{target.full_name} теперь может писать 🗣")
    await log_action(f"🔊 {user.full_name} анмутнул {target.full_name}", context)


# ——————————— KICK / BAN ———————————
async def kick(update, context):
    chat = update.effective_chat
    user = update.effective_user

    lvl = await get_level(chat.id, user.id)
    if not check_level(lvl, 3):
        return await update.message.reply_text("Недостаточно прав.")

    target = await get_target(update, context)
    if not target:
        return await update.message.reply_text("Не найден.")

    if await get_level(chat.id, target.id) >= lvl:
        return await update.message.reply_text("Нельзя трогать равного/старшего.")

    await chat.ban_member(target.id, until_date=datetime.utcnow() + timedelta(seconds=5))
    await update.message.reply_text(f"{target.full_name} был кикнут 👢")
    await log_action(f"👢 {user.full_name} кикнул {target.full_name}", context)


async def ban(update, context):
    chat = update.effective_chat
    user = update.effective_user
    lvl = await get_level(chat.id, user.id)

    if not check_level(lvl, 4):
        return await update.message.reply_text("Баны доступны с уровня 4.")

    target = await get_target(update, context)
    if not target:
        return await update.message.reply_text("Не найден.")

    if await get_level(chat.id, target.id) >= lvl:
        return await update.message.reply_text("Ты не можешь банить равного/старшего.")

    await chat.ban_member(target.id)
    await update.message.reply_text(f"{target.full_name} забанен 🔥")
    await log_action(f"🔨 {user.full_name} забанил {target.full_name}", context)


async def unban(update, context):
    chat = update.effective_chat
    user = update.effective_user
    lvl = await get_level(chat.id, user.id)

    if not check_level(lvl, 4):
        return await update.message.reply_text("Недостаточно прав.")

    if not context.args:
        return await update.message.reply_text("Укажи ID.")

    uid = int(context.args[0])
    await chat.unban_member(uid)
    await update.message.reply_text(f"{uid} разбанен.")
    await log_action(f"♻ {user.full_name} разбанил {uid}", context)


# ——————————— GREETING ———————————
async def greet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.chat_member
    old, new = data.old_chat_member, data.new_chat_member

    if old.status in ("left", "kicked") and new.status in ("member", "restricted", "administrator"):
        u = new.user
        chat = update.effective_chat

        rules = await get_rules(chat.id) or DEFAULT_RULES
        msg = WELCOME_TEXT.format(name=u.first_name, chat=chat.title)
        msg += "\n\n" + rules

        await context.bot.send_message(chat.id, msg)


# ——————————— ANTIFLOOD (simple) ———————————
spam_cache = {}

async def antiflood(update, context):
    user = update.effective_user
    chat = update.effective_chat
    now = datetime.utcnow().timestamp()

    key = f"{chat.id}:{user.id}"
    last = spam_cache.get(key, 0)

    if now - last < 0.6:
        lvl = await get_level(chat.id, user.id)
        if lvl < 2:
            await update.message.delete()
            return
    spam_cache[key] = now


# —————————————————— MAIN ——————————————————
async def main():
    await init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("setrules", setrules))
    app.add_handler(CommandHandler("setlevel", setlevel))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("warns", warns_list))
    app.add_handler(CommandHandler("clearwarns", clearwarns))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))

    app.add_handler(ChatMemberHandler(greet, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), antiflood))

    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
