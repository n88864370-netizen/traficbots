# bot.py
# -*- coding: utf-8 -*-
"""
Спрощений телеграм-бот для арбітраж-команди:
- Стартове меню: Подати заявку, Перевірити заявку
- "Подати заявку": бот створює персональне інвайт-посилання на канал із заявкою на вступ
- "Перевірити заявку": якщо вже є хоча б одна заявка → відкривається меню арбітражника
- Меню арбітражника: Статистика, Моя реф. ссилка, Заявка на виплату, Зв'язок з власником, Увійти в чат
- SQLite для зберігання статистики

Перед запуском заповніть константи нижче (API_TOKEN, CHANNEL_ID, CHANNEL_LINK, CHAT_LINK, OWNER_ID).
"""

import logging
import sqlite3

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatInviteLink

# ===================== НАЛАШТУВАННЯ =====================
API_TOKEN = "8353432332:AAE-FYyo0oekiSz1BmGizXTh8X0HVD9KPUQ"
CHANNEL_ID = -1002646229900
CHANNEL_LINK = "https://t.me/+6M02Kc1z0t80Y2Zi"
CHAT_LINK = "https://t.me/+bN65FTKvhRllZjAy"
OWNER_ID = 7939185150 

AUTO_APPROVE = True
PAYOUT_PER_REQUEST = 0.40

# ========================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# ===================== БАЗА ДАНИХ =====================
DB_PATH = "arbit_bot.db"

SCHEMA_USERS = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    ref_link TEXT,
    referrals INTEGER DEFAULT 0,
    earnings REAL DEFAULT 0.0
);
"""

SCHEMA_INVITES = """
CREATE TABLE IF NOT EXISTS invite_links (
    invite_link TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL
);
"""


def db_init():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(SCHEMA_USERS)
        cur.execute(SCHEMA_INVITES)
        conn.commit()


def get_user(user_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, ref_link, referrals, earnings FROM users WHERE user_id=?", (user_id,))
        return cur.fetchone()


def ensure_user(user_id: int):
    if not get_user(user_id):
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO users(user_id) VALUES(?)", (user_id,))
            conn.commit()


def set_user_ref_link(user_id: int, link: str):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET ref_link=? WHERE user_id=?", (link, user_id))
        conn.commit()


def upsert_invite_link(invite_link: str, owner_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO invite_links(invite_link, owner_id) VALUES(?, ?)", (invite_link, owner_id))
        conn.commit()


def get_invite_owner(invite_link: str):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT owner_id FROM invite_links WHERE invite_link=?", (invite_link,))
        row = cur.fetchone()
        return row[0] if row else None


def add_referral_and_earn(owner_id: int, amount: float):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET referrals = COALESCE(referrals,0) + 1, earnings = COALESCE(earnings,0) + ? WHERE user_id=?",
            (amount, owner_id),
        )
        conn.commit()

# ===================== КНОПКИ =====================

def start_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📝 Подати заявку", callback_data="submit_request"),
        InlineKeyboardButton("✅ Перевірити заявку", callback_data="check_request"),
    )
    return kb


def arbitrage_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📊 Моя статистика", callback_data="stats"),
        InlineKeyboardButton("🔗 Моя реф. ссилка", callback_data="ref_link"),
        InlineKeyboardButton("💰 Заявка на виплату", callback_data="payout"),
        InlineKeyboardButton("💬 Зв'язок з власником", url=f"tg://user?id={OWNER_ID}"),
        InlineKeyboardButton("💭 Увійти в чат", url=CHAT_LINK),
        InlineKeyboardButton("⬅️ На головну", callback_data="back_to_start"),
    )
    return kb

# ===================== ХЕЛПЕР =====================
async def create_or_get_user_invite(user_id: int) -> str:
    ensure_user(user_id)
    row = get_user(user_id)
    if row and row[1]:
        return row[1]

    link_obj: ChatInviteLink = await bot.create_chat_invite_link(
        chat_id=CHANNEL_ID,
        name=f"ref_{user_id}",
        creates_join_request=True,
    )
    link = link_obj.invite_link
    set_user_ref_link(user_id, link)
    upsert_invite_link(link, owner_id=user_id)
    return link

# ===================== ХЕНДЛЕРИ =====================
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    ensure_user(message.from_user.id)
    await message.answer("👋 Вітаю! Обери дію:", reply_markup=start_kb())


@dp.callback_query_handler(lambda c: c.data == "back_to_start")
async def back_to_start(callback: types.CallbackQuery):
    await callback.message.edit_text("👋 Вітаю! Обери дію:", reply_markup=start_kb())


@dp.callback_query_handler(lambda c: c.data == "submit_request")
async def submit_request(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    link = await create_or_get_user_invite(user_id)
    await callback.message.edit_text(
        f"🔗 Твоя реф. ссилка для подання заявок:\n{link}\n\nЧекай, поки по ній подадуть заявку.",
        reply_markup=start_kb(),
    )


@dp.callback_query_handler(lambda c: c.data == "check_request")
async def check_request(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    row = get_user(user_id)
    referrals = (row[2] if row else 0) or 0

    if referrals > 0:
        await callback.message.edit_text("🔓 Заявка подана! Доступ до меню арбітражника:", reply_markup=arbitrage_kb())
    else:
        await callback.message.edit_text("❗️ Заявок ще немає. Поділись своєю ссилкою та зачекай.", reply_markup=start_kb())


@dp.callback_query_handler(lambda c: c.data == "ref_link")
async def show_ref_link(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    link = await create_or_get_user_invite(user_id)
    await callback.message.edit_text(f"🔗 Твоя реф. ссилка:\n{link}", reply_markup=arbitrage_kb())


@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    row = get_user(user_id)
    referrals = (row[2] if row else 0) or 0
    earnings = (row[3] if row else 0.0) or 0.0
    text = f"📊 <b>Твоя статистика</b>:\n🔢 Заявок: {referrals}\n💵 Заробіток: {earnings:.2f} $"
    await callback.message.edit_text(text, reply_markup=arbitrage_kb())


@dp.callback_query_handler(lambda c: c.data == "payout")
async def payout(callback: types.CallbackQuery):
    await callback.message.edit_text("💰 Для виплати зв'яжись з власником:", reply_markup=arbitrage_kb())


# ===================== ОБРОБКА ЗАЯВОК НА ВСТУП =====================
@dp.chat_join_request_handler()
async def handle_join_request(join_req: types.ChatJoinRequest):
    try:
        inv: ChatInviteLink = join_req.invite_link
        link_str = inv.invite_link if inv else None
        applicant = join_req.from_user
        owner_id = get_invite_owner(link_str) if link_str else None

        if owner_id:
            add_referral_and_earn(owner_id, PAYOUT_PER_REQUEST)
            try:
                await bot.send_message(
                    owner_id,
                    f"🆕 Нова заявка по твоїй ссилці!\nВід: {applicant.full_name} (@{applicant.username or '—'})"
                )
            except Exception:
                pass

        if AUTO_APPROVE:
            await bot.approve_chat_join_request(chat_id=join_req.chat.id, user_id=applicant.id)

    except Exception as e:
        logger.exception("Помилка обробки заявки: %s", e)


# ===================== ЗАПУСК =====================
if __name__ == "__main__":
    db_init()
    logger.info("Бот запущено…")
    executor.start_polling(dp, skip_updates=True)
