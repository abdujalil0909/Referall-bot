"""
TELEGRAM REFERRAL BOT - To'liq versiya
- Referal tizimi
- Majburiy obuna
- Admin panel
- Stars chiqarish (ball -> Stars)
- Stars sotib olish (Payme/Click/Uzcard -> Stars)
"""

import logging
import sqlite3
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ============================================================
#                      SOZLAMALAR
# ============================================================
BOT_TOKEN = "8737368029:AAE2KTU2JFOciubriLQpFkAnquTPKCG8VBs"
BOT_USERNAME = "Abu_referal_bot"   # @ belgisisiz
ADMIN_IDS = [7007573815]

# Referal mukofoti
REWARD_PER_REFERRAL = 10             # har referal uchun ball

# Stars chiqarish (ball -> Stars)
MIN_WITHDRAW_BALLS = 100             # minimum chiqarish ball
BALL_TO_STARS = 10                   # 10 ball = 1 Stars

# Stars sotib olish paketlari (Stars miqdori: narx so'mda) — DB da saqlanadi, bu default
STAR_PACKAGES_DEFAULT = {
    50:   12000,
    75:   17000,
    100:  22000,
    150:  32000,
    250:  50000,
    500:  100000,
    1000: 200000,
    2500: 530000,
}

# Isbot kanali (isbotlar yuboriladigan kanal ID yoki @username)
# Masalan: "@isbot_kanal" yoki "-1001234567890"
PROOF_CHANNEL = "@isbot_kanal"   # ← o'z kanalingizni kiriting

# To'lov rekvizitlari
PAYMENT_INFO = """
💳 <b>To'lov rekvizitlari:</b>

🏦 Karta: <code>8600 1234 5678 9012</code>
👤 Egasi: Ism Familiya
🏧 Payme: +998901234567
🏧 Click: +998901234567

⚠️ To'lov izohiga <b>Telegram ID</b> ingizni yozing!
"""
# ============================================================

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
DB_PATH = "bot.db"

# States
WAIT_BROADCAST = "broadcast"
WAIT_ADD_CH = "add_channel"
WAIT_REWARD = "set_reward"
WAIT_ADD_BAL_ID = "add_bal_id"
WAIT_ADD_BAL_AMT = "add_bal_amt"
WAIT_REM_BAL_ID = "rem_bal_id"
WAIT_REM_BAL_AMT = "rem_bal_amt"
WAIT_WITHDRAW = "withdraw_amount"
WAIT_BUY_RECEIPT = "buy_receipt"     # Chek rasmi kutish
WAIT_PKG_STARS = "pkg_stars"         # Paket Stars miqdori
WAIT_PKG_PRICE = "pkg_price"         # Paket narxi
WAIT_CARD_NUMBER = "card_number"     # Karta raqami
WAIT_CARD_NAME = "card_name"         # Karta egasi
WAIT_CARD_PAYME = "card_payme"       # Payme raqami
WAIT_CARD_CLICK = "card_click"       # Click raqami

# ============================================================
#                      DATABASE
# ============================================================

def db_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    con = db_conn()
    c = con.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, name TEXT, username TEXT,
        balance INTEGER DEFAULT 0, referrals INTEGER DEFAULT 0,
        referred_by INTEGER, joined_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id TEXT UNIQUE)""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, name TEXT, username TEXT,
        balls INTEGER, stars INTEGER,
        status TEXT DEFAULT 'pending', created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS buy_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, name TEXT, username TEXT,
        stars INTEGER, amount INTEGER,
        receipt_file_id TEXT,
        status TEXT DEFAULT 'pending', created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS star_packages (
        stars INTEGER PRIMARY KEY,
        price INTEGER NOT NULL)""")
    c.execute("INSERT OR IGNORE INTO channels (channel_id) VALUES (?)", ("@Aksiyava",))
    c.execute("INSERT OR IGNORE INTO settings VALUES ('reward', '10')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('card_number', '8600 1234 5678 9012')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('card_name', 'Ism Familiya')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('card_payme', '+998901234567')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('card_click', '+998901234567')")
    # Default paketlarni qo'shish (faqat bo'sh bo'lsa)
    c.execute("SELECT COUNT(*) FROM star_packages")
    if c.fetchone()[0] == 0:
        for stars, price in STAR_PACKAGES_DEFAULT.items():
            c.execute("INSERT INTO star_packages (stars, price) VALUES (?,?)", (stars, price))
    con.commit()
    con.close()

def get_channels():
    con = db_conn()
    c = con.cursor()
    c.execute("SELECT channel_id FROM channels")
    rows = c.fetchall()
    con.close()
    return [r[0] for r in rows]

def add_channel(ch):
    con = db_conn()
    c = con.cursor()
    c.execute("INSERT OR IGNORE INTO channels (channel_id) VALUES (?)", (ch,))
    con.commit()
    con.close()

def remove_channel(ch):
    con = db_conn()
    c = con.cursor()
    c.execute("DELETE FROM channels WHERE channel_id=?", (ch,))
    con.commit()
    con.close()

def get_reward():
    con = db_conn()
    c = con.cursor()
    c.execute("SELECT value FROM settings WHERE key='reward'")
    r = c.fetchone()
    con.close()
    return int(r[0]) if r else 10

def set_reward(val):
    con = db_conn()
    c = con.cursor()
    c.execute("INSERT OR REPLACE INTO settings VALUES ('reward', ?)", (str(val),))
    con.commit()
    con.close()

def get_setting(key, default=""):
    con = db_conn()
    c = con.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    r = c.fetchone()
    con.close()
    return r[0] if r else default

def set_setting(key, value):
    con = db_conn()
    c = con.cursor()
    c.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, str(value)))
    con.commit()
    con.close()

def get_payment_info():
    """DB dan karta ma'lumotlarini olib, to'lov matnini qaytarish."""
    card_number = get_setting("card_number", "8600 1234 5678 9012")
    card_name   = get_setting("card_name",   "Ism Familiya")
    payme       = get_setting("card_payme",  "+998901234567")
    click       = get_setting("card_click",  "+998901234567")
    return (
        f"💳 <b>To'lov rekvizitlari:</b>\n\n"
        f"🏦 Karta: <code>{card_number}</code>\n"
        f"👤 Egasi: {card_name}\n"
        f"🏧 Payme: {payme}\n"
        f"🏧 Click: {click}\n\n"
        f"⚠️ To'lov izohiga <b>Telegram ID</b> ingizni yozing!"
    )

def get_user(uid):
    con = db_conn()
    c = con.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    r = c.fetchone()
    con.close()
    return r

def create_user(uid, name, username, referred_by=None):
    con = db_conn()
    c = con.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT OR IGNORE INTO users (user_id,name,username,referred_by,joined_at) VALUES (?,?,?,?,?)",
              (uid, name, username or "", referred_by, now))
    is_new = c.rowcount > 0
    if is_new and referred_by:
        reward = get_reward()
        c.execute("UPDATE users SET balance=balance+?, referrals=referrals+1 WHERE user_id=?",
                  (reward, referred_by))
    con.commit()
    con.close()
    return is_new

def update_balance(uid, amount):
    con = db_conn()
    c = con.cursor()
    c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, uid))
    con.commit()
    con.close()

def get_all_users():
    con = db_conn()
    c = con.cursor()
    c.execute("SELECT user_id, name, username, balance, referrals, joined_at FROM users")
    rows = c.fetchall()
    con.close()
    return rows

def get_stats():
    con = db_conn()
    c = con.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT SUM(referrals) FROM users")
    refs = c.fetchone()[0] or 0
    c.execute("SELECT SUM(balance) FROM users")
    bal = c.fetchone()[0] or 0
    con.close()
    return total, refs, bal

def get_top(limit=10):
    con = db_conn()
    c = con.cursor()
    c.execute("SELECT name, referrals, balance FROM users ORDER BY referrals DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    con.close()
    return rows

def has_pending_withdrawal(uid):
    con = db_conn()
    c = con.cursor()
    c.execute("SELECT id FROM withdrawals WHERE user_id=? AND status='pending'", (uid,))
    r = c.fetchone()
    con.close()
    return r is not None

def has_pending_buy(uid):
    con = db_conn()
    c = con.cursor()
    c.execute("SELECT id FROM buy_orders WHERE user_id=? AND status='pending'", (uid,))
    r = c.fetchone()
    con.close()
    return r is not None

def create_withdrawal(uid, name, username, balls, stars):
    con = db_conn()
    c = con.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT INTO withdrawals (user_id,name,username,balls,stars,created_at) VALUES (?,?,?,?,?,?)",
              (uid, name, username or "", balls, stars, now))
    wid = c.lastrowid
    c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (balls, uid))
    con.commit()
    con.close()
    return wid

def get_withdrawal(wid):
    con = db_conn()
    c = con.cursor()
    c.execute("SELECT * FROM withdrawals WHERE id=?", (wid,))
    r = c.fetchone()
    con.close()
    return r

def update_withdrawal_status(wid, status):
    con = db_conn()
    c = con.cursor()
    c.execute("UPDATE withdrawals SET status=? WHERE id=?", (status, wid))
    con.commit()
    con.close()

def reject_withdrawal(wid):
    con = db_conn()
    c = con.cursor()
    c.execute("SELECT user_id, balls FROM withdrawals WHERE id=?", (wid,))
    row = c.fetchone()
    if row:
        c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (row[1], row[0]))
        c.execute("UPDATE withdrawals SET status='rejected' WHERE id=?", (wid,))
    con.commit()
    con.close()
    return row

def create_buy_order(uid, name, username, stars, amount, receipt_file_id):
    con = db_conn()
    c = con.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT INTO buy_orders (user_id,name,username,stars,amount,receipt_file_id,created_at) VALUES (?,?,?,?,?,?,?)",
              (uid, name, username or "", stars, amount, receipt_file_id, now))
    oid = c.lastrowid
    con.commit()
    con.close()
    return oid

def get_buy_order(oid):
    con = db_conn()
    c = con.cursor()
    c.execute("SELECT * FROM buy_orders WHERE id=?", (oid,))
    r = c.fetchone()
    con.close()
    return r

def update_buy_status(oid, status):
    con = db_conn()
    c = con.cursor()
    c.execute("UPDATE buy_orders SET status=? WHERE id=?", (status, oid))
    con.commit()
    con.close()

def get_pending_withdrawals():
    con = db_conn()
    c = con.cursor()
    c.execute("SELECT * FROM withdrawals WHERE status='pending' ORDER BY id DESC")
    rows = c.fetchall()
    con.close()
    return rows

def get_pending_buys():
    con = db_conn()
    c = con.cursor()
    c.execute("SELECT * FROM buy_orders WHERE status='pending' ORDER BY id DESC")
    rows = c.fetchall()
    con.close()
    return rows

# ---- STAR PACKAGES ----
def get_star_packages():
    """DB dan paketlarni olish (tartiblangan)."""
    con = db_conn()
    c = con.cursor()
    c.execute("SELECT stars, price FROM star_packages ORDER BY stars ASC")
    rows = c.fetchall()
    con.close()
    return dict(rows) if rows else STAR_PACKAGES_DEFAULT

def set_star_package(stars, price):
    """Paket narxini yangilash yoki yangi qo'shish."""
    con = db_conn()
    c = con.cursor()
    c.execute("INSERT OR REPLACE INTO star_packages (stars, price) VALUES (?,?)", (stars, price))
    con.commit()
    con.close()

def delete_star_package(stars):
    """Paketni o'chirish."""
    con = db_conn()
    c = con.cursor()
    c.execute("DELETE FROM star_packages WHERE stars=?", (stars,))
    con.commit()
    con.close()

# ============================================================
#                    OBUNA TEKSHIRUV
# ============================================================

async def check_sub(uid, bot):
    not_sub = []
    for ch in get_channels():
        try:
            m = await bot.get_chat_member(ch, uid)
            if m.status in ["left", "kicked"]:
                not_sub.append(ch)
        except Exception as e:
            logger.error(f"Kanal xato {ch}: {e}")
            not_sub.append(ch)
    return not_sub

def sub_keyboard(not_sub):
    btns = [[InlineKeyboardButton(f"📢 {ch}", url=f"https://t.me/{ch.lstrip('@')}")] for ch in not_sub]
    btns.append([InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(btns)

# ============================================================
#                    KLAVIATURALAR
# ============================================================

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Profil", callback_data="profile"),
         InlineKeyboardButton("🔗 Referal", callback_data="referral")],
        [InlineKeyboardButton("⭐ Stars sotib olish", callback_data="buy_stars"),
         InlineKeyboardButton("📤 Stars chiqarish", callback_data="withdraw")],
        [InlineKeyboardButton("🏆 Top 10", callback_data="top"),
         InlineKeyboardButton("ℹ️ Yordam", callback_data="help")],
    ])

def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistika", callback_data="adm_stats"),
         InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="adm_users")],
        [InlineKeyboardButton("📢 Kanallar", callback_data="adm_channels"),
         InlineKeyboardButton("🎁 Mukofot", callback_data="adm_reward")],
        [InlineKeyboardButton("💰 Ball qo'shish", callback_data="adm_add_bal"),
         InlineKeyboardButton("💸 Ball ayirish", callback_data="adm_rem_bal")],
        [InlineKeyboardButton("⭐ Chiqarish so'rovlari", callback_data="adm_withdrawals"),
         InlineKeyboardButton("🛒 Sotib olish so'rovlari", callback_data="adm_buys")],
        [InlineKeyboardButton("💎 Stars narxlari", callback_data="adm_packages"),
         InlineKeyboardButton("💳 Karta ma'lumotlari", callback_data="adm_card")],
        [InlineKeyboardButton("📨 Broadcast", callback_data="adm_broadcast")],
        [InlineKeyboardButton("🏠 Bosh menu", callback_data="home")],
    ])

def channels_kb():
    btns = []
    for ch in get_channels():
        btns.append([InlineKeyboardButton(f"🗑 {ch} — ochirish", callback_data=f"delch_{ch}")])
    btns.append([InlineKeyboardButton("➕ Kanal qoshish", callback_data="adm_add_ch")])
    btns.append([InlineKeyboardButton("⬅️ Admin", callback_data="admin")])
    return InlineKeyboardMarkup(btns)

def packages_kb():
    btns = []
    row = []
    for i, (stars, price) in enumerate(get_star_packages().items()):
        price_str = f"{price:,}".replace(",", " ")
        row.append(InlineKeyboardButton(
            f"⭐{stars} — {price_str} so'm",
            callback_data=f"pkg_{stars}_{price}"
        ))
        if len(row) == 2:
            btns.append(row)
            row = []
    if row:
        btns.append(row)
    btns.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="home")])
    return InlineKeyboardMarkup(btns)

def packages_admin_kb():
    """Admin uchun paketlar ro'yxati — tahrirlash va o'chirish."""
    btns = []
    for stars, price in get_star_packages().items():
        price_str = f"{price:,}".replace(",", " ")
        btns.append([
            InlineKeyboardButton(f"⭐{stars} — {price_str} so'm", callback_data=f"adm_pkg_edit_{stars}"),
            InlineKeyboardButton("🗑", callback_data=f"adm_pkg_del_{stars}"),
        ])
    btns.append([InlineKeyboardButton("➕ Yangi paket qo'shish", callback_data="adm_pkg_add")])
    btns.append([InlineKeyboardButton("⬅️ Admin", callback_data="admin")])
    return InlineKeyboardMarkup(btns)

def back_kb(cb="home"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data=cb)]])

def withdrawal_admin_kb(wid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"wok_{wid}"),
         InlineKeyboardButton("❌ Rad etish", callback_data=f"wno_{wid}")],
    ])

def buy_admin_kb(oid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tasdiqlash (Stars yubordim)", callback_data=f"bok_{oid}"),
         InlineKeyboardButton("❌ Rad etish", callback_data=f"bno_{oid}")],
    ])

async def reply(update, text, kb=None):
    msg = update.callback_query.message if update.callback_query else update.message
    await msg.reply_text(text, reply_markup=kb, parse_mode="HTML")

async def send_proof_to_channel(bot, proof_type: str, user_id, user_name, username, data_dict: dict, photo_file_id=None):
    """Isbot kanalga tasdiqlangan operatsiyani yuborish."""
    if not PROOF_CHANNEL or PROOF_CHANNEL == "@isbot_kanal":
        return  # Kanal sozlanmagan
    uname_str = f"@{username}" if username else "username yo'q"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if proof_type == "withdraw":
        text = (
            f"📤 <b>Stars chiqarish — TASDIQLANDI ✅</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👤 {user_name} ({uname_str})\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"💰 Ball: <b>{data_dict['balls']}</b>\n"
            f"⭐ Stars: <b>{data_dict['stars']}</b>\n"
            f"📅 Sana: {now}"
        )
    elif proof_type == "buy":
        price_str = f"{data_dict['amount']:,}".replace(",", " ")
        text = (
            f"🛒 <b>Stars sotib olish — TASDIQLANDI ✅</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👤 {user_name} ({uname_str})\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"⭐ Stars: <b>{data_dict['stars']}</b>\n"
            f"💳 To'lov: <b>{price_str} so'm</b>\n"
            f"📅 Sana: {now}"
        )
    else:
        return

    try:
        if photo_file_id and proof_type == "buy":
            await bot.send_photo(PROOF_CHANNEL, photo=photo_file_id, caption=text, parse_mode="HTML")
        else:
            await bot.send_message(PROOF_CHANNEL, text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Isbot kanalga yuborishda xato: {e}")

# ============================================================
#                       HANDLERLAR
# ============================================================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referred_by = None
    if context.args and context.args[0].startswith("ref_"):
        try:
            ref_id = int(context.args[0][4:])
            if ref_id != user.id:
                referred_by = ref_id
        except:
            pass

    is_new = create_user(user.id, user.first_name, user.username or "", referred_by)
    not_sub = await check_sub(user.id, context.bot)
    if not_sub:
        await update.message.reply_text(
            "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna buling:",
            reply_markup=sub_keyboard(not_sub))
        return

    reward = get_reward()
    bonus = f"\n\n🎁 Taklif uchun {reward} ball berildi!" if is_new and referred_by else ""
    await update.message.reply_text(
        f"👋 Salom, <b>{user.first_name}</b>!\n\n"
        f"🤖 Referral botga xush kelibsiz!\n\n"
        f"💰 Har bir referal = <b>{reward} ball</b>\n"
        f"⭐ {BALL_TO_STARS} ball = 1 Stars\n"
        f"📤 Minimum chiqarish: <b>{MIN_WITHDRAW_BALLS} ball</b>\n"
        f"🛒 Stars sotib olish ham mavjud!{bonus}",
        reply_markup=main_kb(), parse_mode="HTML")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Ruxsat yoq!")
        return
    await update.message.reply_text("🔧 <b>Admin Panel</b>", reply_markup=admin_kb(), parse_mode="HTML")

async def btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    # Obuna tekshirish
    if data == "check_sub":
        not_sub = await check_sub(user.id, context.bot)
        if not_sub:
            await reply(update, "❌ Hali obuna bolmadingiz!", sub_keyboard(not_sub))
        else:
            reward = get_reward()
            await reply(update,
                f"✅ <b>Obuna tasdiqlandi!</b>\n\n👋 Salom, <b>{user.first_name}</b>!\n💰 Har bir referal = <b>{reward} ball</b>",
                main_kb())
        return

    if data.startswith("adm") and user.id not in ADMIN_IDS:
        await query.answer("❌ Ruxsat yoq!", show_alert=True)
        return

    if not data.startswith("adm") and data not in ["admin", "home", "check_sub"]:
        not_sub = await check_sub(user.id, context.bot)
        if not_sub:
            await reply(update, "⚠️ Avval kanallarga obuna buling:", sub_keyboard(not_sub))
            return

    # ---- BOT MENU ----
    if data == "home":
        reward = get_reward()
        await reply(update, f"🏠 <b>Bosh menu</b>\n💰 Har bir referal = <b>{reward} ball</b>", main_kb())

    elif data == "profile":
        u = get_user(user.id)
        stars_eqv = u[3] // BALL_TO_STARS
        await reply(update,
            f"👤 <b>Profil</b>\n\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"📛 Ism: {u[1]}\n"
            f"👥 Referallar: <b>{u[4]}</b>\n"
            f"💰 Balans: <b>{u[3]} ball</b>\n"
            f"⭐ Stars ekvivalenti: <b>{stars_eqv} Stars</b>\n"
            f"📅 Sana: {u[6]}", back_kb())

    elif data == "referral":
        link = f"https://t.me/{BOT_USERNAME}?start=ref_{user.id}"
        u = get_user(user.id)
        reward = get_reward()
        await reply(update,
            f"🔗 <b>Referal havolangiz:</b>\n\n"
            f"<code>{link}</code>\n\n"
            f"👥 Takliflar: <b>{u[4]}</b>\n"
            f"💰 Balans: <b>{u[3]} ball</b>\n"
            f"🎁 Har referal: <b>{reward} ball</b>", back_kb())

    # ---- STARS SOTIB OLISH ----
    elif data == "buy_stars":
        await reply(update,
            f"🛒 <b>Stars sotib olish</b>\n\n"
            f"Paket tanlang. To'lovdan keyin chek rasmini yuboring.\n"
            f"Admin tasdiqlasa, Stars yuboriladi.\n\n"
            f"💳 To'lov: Payme / Click / Uzcard",
            packages_kb())

    elif data.startswith("pkg_"):
        if has_pending_buy(user.id):
            await reply(update,
                "⏳ Sizda kutilayotgan buyurtma bor!\nAdmin tasdiqlashini kuting.", back_kb())
            return
        parts = data.split("_")
        stars = int(parts[1])
        price = int(parts[2])
        price_str = f"{price:,}".replace(",", " ")
        context.user_data["state"] = WAIT_BUY_RECEIPT
        context.user_data["buy_stars"] = stars
        context.user_data["buy_price"] = price
        await reply(update,
            f"⭐ <b>{stars} Stars</b> — {price_str} so'm\n\n"
            f"{get_payment_info()}\n\n"
            f"✅ To'lovni amalga oshiring, keyin <b>chek rasmini</b> shu chatga yuboring.",
            back_kb("buy_stars"))

    # ---- STARS CHIQARISH ----
    elif data == "withdraw":
        u = get_user(user.id)
        if has_pending_withdrawal(user.id):
            await reply(update, "⏳ Kutilayotgan chiqarish so'rovingiz bor!\nAdmin tasdiqlashini kuting.", back_kb())
            return
        if u[3] < MIN_WITHDRAW_BALLS:
            await reply(update,
                f"📤 <b>Stars chiqarish</b>\n\n"
                f"💰 Sizning balansingiz: <b>{u[3]} ball</b>\n"
                f"📉 Minimum: <b>{MIN_WITHDRAW_BALLS} ball</b>\n\n"
                f"❌ Balansingiz yetarli emas!\n"
                f"Yana <b>{MIN_WITHDRAW_BALLS - u[3]} ball</b> yig'ishingiz kerak.", back_kb())
            return
        context.user_data["state"] = WAIT_WITHDRAW
        stars_eqv = u[3] // BALL_TO_STARS
        await reply(update,
            f"📤 <b>Stars chiqarish</b>\n\n"
            f"💰 Balansingiz: <b>{u[3]} ball</b>\n"
            f"⭐ Ekvivalent: <b>{stars_eqv} Stars</b>\n"
            f"📊 Kurs: {BALL_TO_STARS} ball = 1 Stars\n"
            f"📉 Minimum: <b>{MIN_WITHDRAW_BALLS} ball</b>\n\n"
            f"Necha ball chiqarmoqchisiz?", back_kb())

    elif data == "top":
        tops = get_top()
        medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
        lines = ["🏆 <b>Top 10:</b>\n"]
        for i, (name, refs, bal) in enumerate(tops):
            you = " ← Siz" if name == user.first_name else ""
            lines.append(f"{medals[i]} {name}{you} — {refs} referal | {bal} ball")
        await reply(update, "\n".join(lines) if tops else "Hali hech kim yoq!", back_kb())

    elif data == "help":
        reward = get_reward()
        await reply(update,
            f"ℹ️ <b>Yordam</b>\n\n"
            f"🔗 <b>Referal:</b>\n"
            f"• Havola oling → dostlarga yuboring\n"
            f"• Har qoshilgan odam = {reward} ball\n\n"
            f"⭐ <b>Stars chiqarish:</b>\n"
            f"• {BALL_TO_STARS} ball = 1 Stars\n"
            f"• Minimum: {MIN_WITHDRAW_BALLS} ball\n"
            f"• So'rov → Admin tasdiqlaydi → Stars olasiz\n\n"
            f"🛒 <b>Stars sotib olish:</b>\n"
            f"• Paket tanlang → Karta bilan toing\n"
            f"• Chek yuboring → Admin Stars yuboradi\n\n"
            f"📢 Botdan foydalanish uchun kanallarga obuna buling.", back_kb())

    # ---- ADMIN ----
    elif data == "admin":
        if user.id not in ADMIN_IDS:
            await query.answer("❌ Ruxsat yoq!", show_alert=True)
            return
        await reply(update, "🔧 <b>Admin Panel</b>", admin_kb())

    elif data == "adm_stats":
        total, refs, bal = get_stats()
        channels = get_channels()
        reward = get_reward()
        pw = len(get_pending_withdrawals())
        pb = len(get_pending_buys())
        await reply(update,
            f"📊 <b>Statistika</b>\n\n"
            f"👥 Foydalanuvchilar: <b>{total}</b>\n"
            f"🔗 Jami referallar: <b>{refs}</b>\n"
            f"💰 Jami ballar: <b>{bal}</b>\n"
            f"📤 Chiqarish so'rovlari: <b>{pw}</b>\n"
            f"🛒 Sotib olish so'rovlari: <b>{pb}</b>\n"
            f"🎁 Mukofot: <b>{reward} ball</b>\n"
            f"📢 Kanallar: {', '.join(channels) if channels else 'Yoq'}", back_kb("admin"))

    elif data == "adm_users":
        users = get_all_users()
        lines = [f"👥 <b>Foydalanuvchilar ({len(users)} ta):</b>\n"]
        for u in users[:20]:
            uname = f"@{u[2]}" if u[2] else "—"
            lines.append(f"• {u[1]} | {uname} | 💰{u[3]} | 👥{u[4]}")
        await reply(update, "\n".join(lines), back_kb("admin"))

    elif data == "adm_channels":
        channels = get_channels()
        text = "📢 <b>Majburiy kanallar:</b>\n\n" + ("\n".join(channels) if channels else "Kanal yoq")
        await reply(update, text, channels_kb())

    elif data.startswith("delch_"):
        ch = data[6:]
        remove_channel(ch)
        channels = get_channels()
        text = f"✅ <b>{ch}</b> ochirildi!\n\n📢 Kanallar:\n" + ("\n".join(channels) if channels else "Kanal yoq")
        await reply(update, text, channels_kb())

    elif data == "adm_add_ch":
        context.user_data["state"] = WAIT_ADD_CH
        await reply(update, "➕ Yangi kanal username kiriting:\nMasalan: <code>@kanal_nomi</code>", back_kb("adm_channels"))

    elif data == "adm_reward":
        reward = get_reward()
        context.user_data["state"] = WAIT_REWARD
        await reply(update, f"🎁 Hozirgi mukofot: <b>{reward} ball</b>\n\nYangi miqdor kiriting:", back_kb("admin"))

    elif data == "adm_add_bal":
        context.user_data["state"] = WAIT_ADD_BAL_ID
        await reply(update, "💰 Ball qoshish\n\nFoydalanuvchi ID sini kiriting:", back_kb("admin"))

    elif data == "adm_rem_bal":
        context.user_data["state"] = WAIT_REM_BAL_ID
        await reply(update, "💸 Ball ayirish\n\nFoydalanuvchi ID sini kiriting:", back_kb("admin"))

    elif data == "adm_broadcast":
        context.user_data["state"] = WAIT_BROADCAST
        await reply(update, "📨 Barcha foydalanuvchilarga yuboriladigan xabarni yozing:", back_kb("admin"))

    # ---- STARS NARXLARI BOSHQARUVI ----
    elif data == "adm_packages":
        pkgs = get_star_packages()
        lines = ["💎 <b>Stars paketlari:</b>\n"]
        for stars, price in pkgs.items():
            price_str = f"{price:,}".replace(",", " ")
            lines.append(f"⭐ {stars} Stars — {price_str} so'm")
        await reply(update, "\n".join(lines), packages_admin_kb())

    elif data.startswith("adm_pkg_edit_"):
        stars = int(data[13:])
        pkgs = get_star_packages()
        price = pkgs.get(stars, "?")
        price_str = f"{price:,}".replace(",", " ") if isinstance(price, int) else price
        context.user_data["state"] = WAIT_PKG_PRICE
        context.user_data["edit_pkg_stars"] = stars
        await reply(update,
            f"✏️ <b>⭐ {stars} Stars</b> paketini tahrirlash\n\n"
            f"Hozirgi narx: <b>{price_str} so'm</b>\n\n"
            f"Yangi narxni so'mda kiriting:", back_kb("adm_packages"))

    elif data.startswith("adm_pkg_del_"):
        stars = int(data[12:])
        delete_star_package(stars)
        await reply(update, f"🗑 <b>⭐ {stars} Stars</b> paketi o'chirildi!", packages_admin_kb())

    elif data == "adm_pkg_add":
        context.user_data["state"] = WAIT_PKG_STARS
        await reply(update,
            "➕ <b>Yangi paket qo'shish</b>\n\n"
            "Necha Stars bo'lsin? (faqat raqam kiriting)\n"
            "Masalan: <code>200</code>", back_kb("adm_packages"))

    # ---- KARTA MA'LUMOTLARI ----
    elif data == "adm_card":
        card_number = get_setting("card_number", "—")
        card_name   = get_setting("card_name",   "—")
        payme       = get_setting("card_payme",  "—")
        click       = get_setting("card_click",  "—")
        await reply(update,
            f"💳 <b>Karta ma'lumotlari</b>\n\n"
            f"🏦 Karta raqami: <code>{card_number}</code>\n"
            f"👤 Egasi: {card_name}\n"
            f"🏧 Payme: {payme}\n"
            f"🏧 Click: {click}\n\n"
            f"Tahrirlash uchun tanlang:",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("🏦 Karta raqami", callback_data="adm_card_number")],
                [InlineKeyboardButton("👤 Karta egasi", callback_data="adm_card_name")],
                [InlineKeyboardButton("🏧 Payme raqami", callback_data="adm_card_payme")],
                [InlineKeyboardButton("🏧 Click raqami", callback_data="adm_card_click")],
                [InlineKeyboardButton("⬅️ Admin", callback_data="admin")],
            ]))

    elif data == "adm_card_number":
        context.user_data["state"] = WAIT_CARD_NUMBER
        cur = get_setting("card_number", "—")
        await reply(update,
            f"🏦 <b>Karta raqamini kiriting</b>\n\nHozirgi: <code>{cur}</code>",
            back_kb("adm_card"))

    elif data == "adm_card_name":
        context.user_data["state"] = WAIT_CARD_NAME
        cur = get_setting("card_name", "—")
        await reply(update,
            f"👤 <b>Karta egasini kiriting</b>\n\nHozirgi: {cur}",
            back_kb("adm_card"))

    elif data == "adm_card_payme":
        context.user_data["state"] = WAIT_CARD_PAYME
        cur = get_setting("card_payme", "—")
        await reply(update,
            f"🏧 <b>Payme raqamini kiriting</b>\n\nHozirgi: {cur}",
            back_kb("adm_card"))

    elif data == "adm_card_click":
        context.user_data["state"] = WAIT_CARD_CLICK
        cur = get_setting("card_click", "—")
        await reply(update,
            f"🏧 <b>Click raqamini kiriting</b>\n\nHozirgi: {cur}",
            back_kb("adm_card"))

    # ---- CHIQARISH SO'ROVLARI ----
    elif data == "adm_withdrawals":
        pending = get_pending_withdrawals()
        if not pending:
            await reply(update, "📤 Kutilayotgan chiqarish so'rovlari yoq.", back_kb("admin"))
            return
        await reply(update, f"📤 <b>{len(pending)} ta chiqarish so'rovi:</b>", back_kb("admin"))
        for w in pending[:10]:
            wid, uid, name, uname, balls, stars, status, created = w
            uname_str = f"@{uname}" if uname else "—"
            await query.message.reply_text(
                f"📤 <b>Chiqarish #{wid}</b>\n\n"
                f"👤 {name} ({uname_str})\n"
                f"🆔 ID: <code>{uid}</code>\n"
                f"💰 Ball: <b>{balls}</b>\n"
                f"⭐ Stars: <b>{stars}</b>\n"
                f"📅 {created}",
                reply_markup=withdrawal_admin_kb(wid), parse_mode="HTML")

    elif data.startswith("wok_"):
        wid = int(data[4:])
        w = get_withdrawal(wid)
        if not w or w[6] != "pending":
            await reply(update, "⚠️ So'rov topilmadi yoki allaqachon korib chiqilgan!")
            return
        update_withdrawal_status(wid, "approved")
        uid, name, uname = w[1], w[2], w[3]
        balls, stars = w[4], w[5]
        try:
            await context.bot.send_message(uid,
                f"✅ <b>Stars chiqarish tasdiqlandi!</b>\n\n"
                f"💰 Ayirildi: <b>{balls} ball</b>\n"
                f"⭐ Stars: <b>{stars}</b>\n\n"
                f"Admin tez orada Stars yuboradi!", parse_mode="HTML")
        except:
            pass
        # Isbot kanalga yuborish
        await send_proof_to_channel(context.bot, "withdraw", uid, name, uname,
                                    {"balls": balls, "stars": stars})
        await reply(update,
            f"✅ #{wid} tasdiqlandi!\n"
            f"👤 {name} ga <b>{stars} Stars</b> yuborishni unutmang!\n"
            f"🆔 <code>{uid}</code>")

    elif data.startswith("wno_"):
        wid = int(data[4:])
        w = get_withdrawal(wid)
        if not w or w[6] != "pending":
            await reply(update, "⚠️ So'rov topilmadi yoki allaqachon korib chiqilgan!")
            return
        row = reject_withdrawal(wid)
        uid, balls = row[0], row[1]
        name = w[2]
        try:
            await context.bot.send_message(uid,
                f"❌ <b>Chiqarish so'rovi rad etildi.</b>\n\n"
                f"💰 <b>{balls} ball</b> balansingizga qaytarildi.", parse_mode="HTML")
        except:
            pass
        await reply(update, f"❌ #{wid} rad etildi. {balls} ball {name} ga qaytarildi.")

    # ---- SOTIB OLISH SO'ROVLARI ----
    elif data == "adm_buys":
        pending = get_pending_buys()
        if not pending:
            await reply(update, "🛒 Kutilayotgan sotib olish so'rovlari yoq.", back_kb("admin"))
            return
        await reply(update, f"🛒 <b>{len(pending)} ta so'rov:</b>", back_kb("admin"))
        for o in pending[:10]:
            oid, uid, name, uname, stars, amount, receipt, status, created = o
            uname_str = f"@{uname}" if uname else "—"
            price_str = f"{amount:,}".replace(",", " ")
            try:
                await context.bot.send_photo(
                    query.message.chat_id,
                    photo=receipt,
                    caption=(
                        f"🛒 <b>Sotib olish #{oid}</b>\n\n"
                        f"👤 {name} ({uname_str})\n"
                        f"🆔 ID: <code>{uid}</code>\n"
                        f"⭐ Stars: <b>{stars}</b>\n"
                        f"💳 Summa: <b>{price_str} so'm</b>\n"
                        f"📅 {created}"
                    ),
                    reply_markup=buy_admin_kb(oid),
                    parse_mode="HTML"
                )
            except:
                await query.message.reply_text(
                    f"🛒 <b>Sotib olish #{oid}</b>\n"
                    f"👤 {name} | ⭐{stars} | 💳{price_str} so'm\n"
                    f"🆔 <code>{uid}</code>",
                    reply_markup=buy_admin_kb(oid), parse_mode="HTML")

    elif data.startswith("bok_"):
        oid = int(data[4:])
        o = get_buy_order(oid)
        if not o or o[7] != "pending":
            await reply(update, "⚠️ So'rov topilmadi yoki allaqachon korib chiqilgan!")
            return
        update_buy_status(oid, "approved")
        uid, name, stars, amount = o[1], o[2], o[4], o[5]
        receipt_file_id = o[6]
        uname = o[3]
        price_str = f"{amount:,}".replace(",", " ")
        try:
            await context.bot.send_message(uid,
                f"✅ <b>To'lovingiz tasdiqlandi!</b>\n\n"
                f"⭐ <b>{stars} Stars</b> tez orada yuboriladi!\n"
                f"💳 To'langan: {price_str} so'm\n\n"
                f"Rahmat!", parse_mode="HTML")
        except:
            pass
        # Isbot kanalga chek bilan yuborish
        await send_proof_to_channel(context.bot, "buy", uid, name, uname,
                                    {"stars": stars, "amount": amount}, receipt_file_id)
        await reply(update,
            f"✅ #{oid} tasdiqlandi!\n"
            f"👤 {name} ga <b>{stars} Stars</b> yuborishni unutmang!\n"
            f"🆔 <code>{uid}</code>")

    elif data.startswith("bno_"):
        oid = int(data[4:])
        o = get_buy_order(oid)
        if not o or o[7] != "pending":
            await reply(update, "⚠️ So'rov topilmadi yoki allaqachon korib chiqilgan!")
            return
        update_buy_status(oid, "rejected")
        uid, name, stars = o[1], o[2], o[4]
        try:
            await context.bot.send_message(uid,
                f"❌ <b>To'lovingiz tasdiqlanmadi.</b>\n\n"
                f"To'lov cheki noto'g'ri yoki summa mos kelmadi.\n"
                f"Qayta urinib ko'ring yoki adminga murojaat qiling.", parse_mode="HTML")
        except:
            pass
        await reply(update, f"❌ #{oid} rad etildi.")


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chek rasmi qabul qilish."""
    user = update.effective_user
    state = context.user_data.get("state")

    if state != WAIT_BUY_RECEIPT:
        return

    stars = context.user_data.get("buy_stars")
    price = context.user_data.get("buy_price")

    if not stars or not price:
        return

    context.user_data.clear()

    if has_pending_buy(user.id):
        await update.message.reply_text("⏳ Sizda kutilayotgan buyurtma bor! Admin tasdiqlashini kuting.")
        return

    # Rasmni olish
    photo = update.message.photo[-1]
    receipt_file_id = photo.file_id

    oid = create_buy_order(user.id, user.first_name, user.username or "", stars, price, receipt_file_id)

    price_str = f"{price:,}".replace(",", " ")
    await update.message.reply_text(
        f"✅ <b>Chekingiz qabul qilindi!</b>\n\n"
        f"⭐ Stars: <b>{stars}</b>\n"
        f"💳 Summa: <b>{price_str} so'm</b>\n\n"
        f"⏳ Admin tekshirib, Stars yuboradi.\n"
        f"Odatda 5-30 daqiqa ichida!",
        reply_markup=main_kb(), parse_mode="HTML")

    # Adminga xabar
    uname_str = f"@{user.username}" if user.username else "username yoq"
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_photo(
                admin_id,
                photo=receipt_file_id,
                caption=(
                    f"🛒 <b>Yangi buyurtma #{oid}</b>\n\n"
                    f"👤 {user.first_name} ({uname_str})\n"
                    f"🆔 ID: <code>{user.id}</code>\n"
                    f"⭐ Stars: <b>{stars}</b>\n"
                    f"💳 Summa: <b>{price_str} so'm</b>"
                ),
                reply_markup=buy_admin_kb(oid),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Admin ga xabar yuborishda xato: {e}")


async def msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    state = context.user_data.get("state")

    if not state:
        return

    if state == WAIT_BUY_RECEIPT:
        await update.message.reply_text("📸 Iltimos, to'lov chekini <b>rasm</b> sifatida yuboring!", parse_mode="HTML")
        return

    if state == WAIT_WITHDRAW:
        context.user_data.clear()
        u = get_user(user.id)
        try:
            balls = int(text.strip())
            if balls < MIN_WITHDRAW_BALLS:
                await update.message.reply_text(f"❌ Minimum {MIN_WITHDRAW_BALLS} ball kiriting!")
                return
            if balls > u[3]:
                await update.message.reply_text(f"❌ Balansingiz yetarli emas! ({u[3]} ball bor)")
                return
            stars = balls // BALL_TO_STARS
            if stars < 1:
                await update.message.reply_text(f"❌ Juda kam! {BALL_TO_STARS} ball = 1 Stars")
                return
            wid = create_withdrawal(user.id, user.first_name, user.username or "", balls, stars)
            await update.message.reply_text(
                f"📤 <b>Chiqarish so'rovi yuborildi!</b>\n\n"
                f"💰 Ball: <b>{balls}</b>\n"
                f"⭐ Stars olasiz: <b>{stars}</b>\n"
                f"⏳ Admin tasdiqlashini kuting...",
                reply_markup=main_kb(), parse_mode="HTML")
            uname_str = f"@{user.username}" if user.username else "username yoq"
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(admin_id,
                        f"📤 <b>Yangi chiqarish so'rovi #{wid}</b>\n\n"
                        f"👤 {user.first_name} ({uname_str})\n"
                        f"🆔 ID: <code>{user.id}</code>\n"
                        f"💰 Ball: <b>{balls}</b>\n"
                        f"⭐ Stars: <b>{stars}</b>",
                        reply_markup=withdrawal_admin_kb(wid), parse_mode="HTML")
                except:
                    pass
        except ValueError:
            await update.message.reply_text("❌ Faqat raqam kiriting!")
        return

    if user.id not in ADMIN_IDS:
        return

    if state == WAIT_BROADCAST:
        context.user_data.clear()
        users = get_all_users()
        sent, fail = 0, 0
        await update.message.reply_text(f"📨 {len(users)} ta foydalanuvchiga yuborilmoqda...")
        for u in users:
            try:
                await context.bot.send_message(u[0], text, parse_mode="HTML")
                sent += 1
                await asyncio.sleep(0.05)
            except:
                fail += 1
        await update.message.reply_text(
            f"✅ Tugadi! Yuborildi: {sent} | Xato: {fail}",
            reply_markup=back_kb("admin"), parse_mode="HTML")

    elif state == WAIT_ADD_CH:
        context.user_data.clear()
        ch = text.strip()
        if not ch.startswith("@"):
            ch = "@" + ch
        add_channel(ch)
        await update.message.reply_text(f"✅ <b>{ch}</b> qoshildi!", reply_markup=back_kb("adm_channels"), parse_mode="HTML")

    elif state == WAIT_REWARD:
        context.user_data.clear()
        try:
            val = int(text.strip())
            set_reward(val)
            await update.message.reply_text(f"✅ Mukofot <b>{val} ball</b> ga ozgartirildi!", reply_markup=back_kb("admin"), parse_mode="HTML")
        except:
            await update.message.reply_text("❌ Faqat raqam kiriting!")

    elif state == WAIT_ADD_BAL_ID:
        try:
            uid = int(text.strip())
            u = get_user(uid)
            if u:
                context.user_data["state"] = WAIT_ADD_BAL_AMT
                context.user_data["target_id"] = uid
                await update.message.reply_text(f"👤 <b>{u[1]}</b> | Balans: <b>{u[3]} ball</b>\n\nQancha ball qoshish?", parse_mode="HTML")
            else:
                await update.message.reply_text("❌ Foydalanuvchi topilmadi!")
        except:
            await update.message.reply_text("❌ Faqat ID raqam kiriting!")

    elif state == WAIT_ADD_BAL_AMT:
        uid = context.user_data.get("target_id")
        context.user_data.clear()
        try:
            amount = int(text.strip())
            update_balance(uid, amount)
            await update.message.reply_text(f"✅ <b>{amount} ball</b> qoshildi!", reply_markup=back_kb("admin"), parse_mode="HTML")
        except:
            await update.message.reply_text("❌ Faqat raqam kiriting!")

    elif state == WAIT_REM_BAL_ID:
        try:
            uid = int(text.strip())
            u = get_user(uid)
            if u:
                context.user_data["state"] = WAIT_REM_BAL_AMT
                context.user_data["target_id"] = uid
                await update.message.reply_text(f"👤 <b>{u[1]}</b> | Balans: <b>{u[3]} ball</b>\n\nQancha ball ayirish?", parse_mode="HTML")
            else:
                await update.message.reply_text("❌ Foydalanuvchi topilmadi!")
        except:
            await update.message.reply_text("❌ Faqat ID raqam kiriting!")

    elif state == WAIT_REM_BAL_AMT:
        uid = context.user_data.get("target_id")
        context.user_data.clear()
        try:
            amount = int(text.strip())
            update_balance(uid, -amount)
            await update.message.reply_text(f"✅ <b>{amount} ball</b> ayirildi!", reply_markup=back_kb("admin"), parse_mode="HTML")
        except:
            await update.message.reply_text("❌ Faqat raqam kiriting!")

    elif state == WAIT_PKG_STARS:
        try:
            stars = int(text.strip())
            if stars <= 0:
                await update.message.reply_text("❌ Stars miqdori musbat raqam bo'lishi kerak!")
                return
            context.user_data["state"] = WAIT_PKG_PRICE
            context.user_data["edit_pkg_stars"] = stars
            await update.message.reply_text(
                f"⭐ <b>{stars} Stars</b> paketi uchun narx kiriting (so'mda):\n"
                f"Masalan: <code>18000</code>", parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("❌ Faqat raqam kiriting!")

    elif state == WAIT_PKG_PRICE:
        stars = context.user_data.get("edit_pkg_stars")
        context.user_data.clear()
        try:
            price = int(text.strip())
            if price <= 0:
                await update.message.reply_text("❌ Narx musbat raqam bo'lishi kerak!")
                return
            set_star_package(stars, price)
            price_str = f"{price:,}".replace(",", " ")
            await update.message.reply_text(
                f"✅ <b>⭐ {stars} Stars</b> — <b>{price_str} so'm</b> ga yangilandi!",
                reply_markup=packages_admin_kb(), parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("❌ Faqat raqam kiriting!")

    elif state == WAIT_CARD_NUMBER:
        context.user_data.clear()
        val = text.strip()
        set_setting("card_number", val)
        await update.message.reply_text(
            f"✅ Karta raqami yangilandi:\n<code>{val}</code>",
            reply_markup=back_kb("adm_card"), parse_mode="HTML")

    elif state == WAIT_CARD_NAME:
        context.user_data.clear()
        val = text.strip()
        set_setting("card_name", val)
        await update.message.reply_text(
            f"✅ Karta egasi yangilandi: <b>{val}</b>",
            reply_markup=back_kb("adm_card"), parse_mode="HTML")

    elif state == WAIT_CARD_PAYME:
        context.user_data.clear()
        val = text.strip()
        set_setting("card_payme", val)
        await update.message.reply_text(
            f"✅ Payme raqami yangilandi: <b>{val}</b>",
            reply_markup=back_kb("adm_card"), parse_mode="HTML")

    elif state == WAIT_CARD_CLICK:
        context.user_data.clear()
        val = text.strip()
        set_setting("card_click", val)
        await update.message.reply_text(
            f"✅ Click raqami yangilandi: <b>{val}</b>",
            reply_markup=back_kb("adm_card"), parse_mode="HTML")

# ============================================================
#                         MAIN
# ============================================================

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CallbackQueryHandler(btn))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_handler))
    print("✅ Bot ishga tushdi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    import time
    while True:
        try:
            main()
        except Exception as e:
            logger.error(f"Bot to'xtadi: {e}")
            print(f"⚠️ Xato: {e} — 5 soniyadan keyin qayta ishga tushadi...")
            time.sleep(5)
