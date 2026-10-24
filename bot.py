import os
import time
import sqlite3
import asyncio
import logging
from html import escape

import aiohttp
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
LIKE_API_URL = os.getenv("LIKE_API_URL", "").strip().rstrip("/")
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
DB_PATH = os.getenv("DB_PATH", "bot.sqlite3")
DAILY_BONUS = max(0, int(os.getenv("DAILY_BONUS", "5")))
LIKE_COST = max(0, int(os.getenv("LIKE_COST", "1")))
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "25"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("fast-like-bot")

MAIN_KB = ReplyKeyboardMarkup([
    [KeyboardButton("❤️  Send Likes"), KeyboardButton("👤  My Profile")],
    [KeyboardButton("🎁  Daily Bonus"), KeyboardButton("🎟️  Redeem Code")],
    [KeyboardButton("🏆  Leaderboard"), KeyboardButton("📊  Statistics")],
    [KeyboardButton("ℹ️  Help")],
], resize_keyboard=True, is_persistent=True, input_field_placeholder="Choose an option…")
ADMIN_KB = ReplyKeyboardMarkup([
    [KeyboardButton("👥  Total Users"), KeyboardButton("🪙  Manage Points")],
    [KeyboardButton("🎟️  Create Redeem Code"), KeyboardButton("📢  Broadcast")],
    [KeyboardButton("⬅️  Main Menu")],
], resize_keyboard=True, is_persistent=True)
REGIONS = ["BD", "IND", "BR", "US", "SAC", "NA", "RU"]
REGION_KB = ReplyKeyboardMarkup(
    [[KeyboardButton(r) for r in REGIONS[i:i+3]] for i in range(0, len(REGIONS), 3)] +
    [[KeyboardButton("❌ Cancel")]], resize_keyboard=True, is_persistent=True)
CANCEL_KB = ReplyKeyboardMarkup([[KeyboardButton("❌ Cancel")]], resize_keyboard=True)

def db():
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(
          user_id INTEGER PRIMARY KEY, username TEXT DEFAULT '', first_name TEXT DEFAULT '',
          points INTEGER NOT NULL DEFAULT 0, last_bonus INTEGER NOT NULL DEFAULT 0,
          joined_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS redeem_codes(
          code TEXT PRIMARY KEY, points INTEGER NOT NULL, max_uses INTEGER NOT NULL,
          uses INTEGER NOT NULL DEFAULT 0, created_by INTEGER NOT NULL, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS redeemed(
          user_id INTEGER NOT NULL, code TEXT NOT NULL, redeemed_at INTEGER NOT NULL,
          PRIMARY KEY(user_id, code)
        );
        CREATE TABLE IF NOT EXISTS requests(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, uid TEXT NOT NULL,
          region TEXT NOT NULL, status TEXT NOT NULL, result TEXT DEFAULT '', created_at INTEGER NOT NULL
        );
        """)

def register(user):
    with db() as con:
        con.execute("""INSERT INTO users(user_id,username,first_name,joined_at) VALUES(?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name""",
        (user.id, user.username or "", user.first_name or "", int(time.time())))

def get_user(uid):
    with db() as con:
        return con.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()

def is_admin(uid):
    return uid in ADMIN_IDS

def header(title, subtitle=""):
    return f"✨ <b>{escape(title)}</b>\n{('<i>'+escape(subtitle)+'</i>\\n\\n') if subtitle else '\\n'}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register(update.effective_user)
    context.user_data.clear()
    name = escape(update.effective_user.first_name or "Player")
    await update.effective_message.reply_text(
        f"⚡ <b>FAST LIKE</b> ⚡\n"
        f"<i>FREE FIRE LIKE ASSISTANT</i>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👋 Welcome, <b>{name}</b>!\n\n"
        "❤️ <b>Fast Like Requests</b>\n"
        "🎁 Daily Bonus & Rewards\n"
        "🪙 Points and Redeem Codes\n"
        "🏆 Community Leaderboard\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "👤 <b>YOUR ACCOUNT</b>\n"
        f"🆔 User ID: <code>{update.effective_user.id}</code>\n"
        f"🪙 Daily Bonus: <b>+{DAILY_BONUS} points</b>\n"
        f"❤️ Request Cost: <b>{LIKE_COST} point(s)</b>\n\n"
        "👇 <b>Choose an option from the menu below.</b>\n\n"
        "<i>⚡ Powered by FAST LIKE</i>",
        parse_mode=ParseMode.HTML, reply_markup=MAIN_KB)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "📘 <b>FAST LIKE • HELP CENTER</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "❤️ <b>Send Likes</b>\n"
        "1. Tap Send Likes.\n2. Enter the player's UID.\n"
        "3. Choose the correct region.\n4. Wait for the API response.\n\n"
        "🎁 <b>Daily Bonus</b> — claim once every 24 hours.\n"
        "🎟️ <b>Redeem Code</b> — enter a code from an admin.\n"
        "👤 <b>My Profile</b> — view your points and requests.\n"
        "🏆 <b>Leaderboard</b> — view top point balances.\n\n"
        "🪙 Points are deducted only when the API confirms success.\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⚠️ Results depend on the API and game service.",
        parse_mode=ParseMode.HTML, reply_markup=MAIN_KB)

async def send_likes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["flow"] = "uid"
    await update.effective_message.reply_text(
        "❤️ <b>FREE FIRE LIKE REQUEST</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🆔 Send the player's numeric UID.\n"
        "📌 UID length: 5–20 digits\n\n"
        "🔒 Please verify the UID before continuing.",
        parse_mode=ParseMode.HTML, reply_markup=CANCEL_KB)

async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid, now = update.effective_user.id, int(time.time())
    with db() as con:
        row = con.execute("SELECT points,last_bonus FROM users WHERE user_id=?", (uid,)).fetchone()
        if not row:
            register(update.effective_user)
            row = con.execute("SELECT points,last_bonus FROM users WHERE user_id=?", (uid,)).fetchone()
        remaining = 86400 - (now - row["last_bonus"])
        if remaining > 0:
            h, rem = divmod(remaining, 3600)
            return await update.effective_message.reply_text(
                f"⏳ <b>Daily Bonus</b>\n\nYou can claim again in <b>{h}h {rem//60}m</b>.",
                parse_mode=ParseMode.HTML, reply_markup=MAIN_KB)
        con.execute("UPDATE users SET points=points+?,last_bonus=? WHERE user_id=?", (DAILY_BONUS, now, uid))
        balance = row["points"] + DAILY_BONUS
    await update.effective_message.reply_text(
        f"🎁 <b>Bonus claimed!</b>\n\n+{DAILY_BONUS} points added.\n🪙 Balance: <b>{balance}</b>",
        parse_mode=ParseMode.HTML, reply_markup=MAIN_KB)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = get_user(uid)
    with db() as con:
        count = con.execute("SELECT COUNT(*) n FROM requests WHERE user_id=?", (uid,)).fetchone()["n"]
        ok = con.execute("SELECT COUNT(*) n FROM requests WHERE user_id=? AND status='SUCCESS'", (uid,)).fetchone()["n"]
    name = escape(u["first_name"] or "Player")
    await update.effective_message.reply_text(
        f"👤 <b>My Profile</b>\n\n"
        f"🙍 Name: {name}\n🆔 User ID: <code>{uid}</code>\n"
        f"🪙 Points: <b>{u['points']}</b>\n📨 Requests: {count}\n✅ Confirmed: {ok}",
        parse_mode=ParseMode.HTML, reply_markup=MAIN_KB)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db() as con:
        rows = con.execute("SELECT first_name,username,points FROM users ORDER BY points DESC LIMIT 10").fetchall()
    lines = ["🏆 <b>FAST LIKE Leaderboard</b>", ""]
    for i, r in enumerate(rows, 1):
        name = escape(r["first_name"] or ("@" + r["username"] if r["username"] else "Player"))
        medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
        lines.append(f"{medal} {name} — <b>{r['points']}</b> pts")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=MAIN_KB)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db() as con:
        users = con.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        total = con.execute("SELECT COUNT(*) n FROM requests").fetchone()["n"]
        success = con.execute("SELECT COUNT(*) n FROM requests WHERE status='SUCCESS'").fetchone()["n"]
    await update.effective_message.reply_text(
        f"📊 <b>Bot Statistics</b>\n\n👥 Users: <b>{users}</b>\n📨 Requests: <b>{total}</b>\n✅ Confirmed: <b>{success}</b>",
        parse_mode=ParseMode.HTML, reply_markup=MAIN_KB)

async def redeem_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["flow"] = "redeem"
    await update.effective_message.reply_text("🎟️ <b>Redeem Code</b>\n\nSend your code:", parse_mode=ParseMode.HTML, reply_markup=CANCEL_KB)

async def redeem(update: Update, code: str):
    uid, now, code = update.effective_user.id, int(time.time()), code.strip().upper()
    with db() as con:
        row = con.execute("SELECT * FROM redeem_codes WHERE code=?", (code,)).fetchone()
        if not row:
            return await update.effective_message.reply_text("❌ Invalid redeem code.", reply_markup=MAIN_KB)
        if row["uses"] >= row["max_uses"]:
            return await update.effective_message.reply_text("❌ This code has reached its limit.", reply_markup=MAIN_KB)
        if con.execute("SELECT 1 FROM redeemed WHERE user_id=? AND code=?", (uid, code)).fetchone():
            return await update.effective_message.reply_text("⚠️ You already redeemed this code.", reply_markup=MAIN_KB)
        con.execute("INSERT INTO redeemed VALUES(?,?,?)", (uid, code, now))
        con.execute("UPDATE redeem_codes SET uses=uses+1 WHERE code=?", (code,))
        con.execute("UPDATE users SET points=points+? WHERE user_id=?", (row["points"], uid))
        balance = con.execute("SELECT points FROM users WHERE user_id=?", (uid,)).fetchone()["points"]
    await update.effective_message.reply_text(f"✅ <b>Code accepted!</b>\n+{row['points']} points\nBalance: <b>{balance}</b>", parse_mode=ParseMode.HTML, reply_markup=MAIN_KB)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.effective_message.reply_text("⛔ Admin access only.", reply_markup=MAIN_KB)
    await update.effective_message.reply_text("🛠️ <b>FAST LIKE Admin Panel</b>\nSelect an action.", parse_mode=ParseMode.HTML, reply_markup=ADMIN_KB)

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    with db() as con: n = con.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
    await update.effective_message.reply_text(f"👥 Total registered users: <b>{n}</b>", parse_mode=ParseMode.HTML, reply_markup=ADMIN_KB)

async def admin_points_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    context.user_data.clear(); context.user_data["flow"] = "admin_points"
    await update.effective_message.reply_text("🪙 Send: <code>USER_ID AMOUNT</code>\nNegative amount removes points.", parse_mode=ParseMode.HTML, reply_markup=ADMIN_KB)

async def create_code_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    context.user_data.clear(); context.user_data["flow"] = "admin_code"
    await update.effective_message.reply_text("🎟️ Send: <code>CODE POINTS MAX_USES</code>\nExample: <code>WELCOME50 50 100</code>", parse_mode=ParseMode.HTML, reply_markup=ADMIN_KB)

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    context.user_data.clear(); context.user_data["flow"] = "admin_broadcast"
    await update.effective_message.reply_text("📢 Send the message you want to broadcast.", reply_markup=ADMIN_KB)

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, user = update.effective_message, update.effective_user
    if not msg or not msg.text: return
    text = msg.text.strip()
    register(user)
    if text == "❌ Cancel":
        context.user_data.clear()
        return await msg.reply_text("Cancelled.", reply_markup=MAIN_KB)
    if text == "⬅️  Main Menu":
        context.user_data.clear()
        return await msg.reply_text("Main menu", reply_markup=MAIN_KB)

    flow = context.user_data.get("flow")
    if flow == "uid":
        if not text.isdigit() or not 5 <= len(text) <= 20:
            return await msg.reply_text("⚠️ UID must be 5–20 digits. Try again.")
        context.user_data["target_uid"] = text; context.user_data["flow"] = "region"
        return await msg.reply_text("🌍 Choose the player's server:", reply_markup=REGION_KB)
    if flow == "region":
        region = text.upper()
        if region not in REGIONS: return await msg.reply_text("Select a region using the buttons.", reply_markup=REGION_KB)
        if not LIKE_API_URL:
            context.user_data.clear()
            return await msg.reply_text("⚙️ Like API is not configured yet. Deploy the API and set LIKE_API_URL.", reply_markup=MAIN_KB)
        if get_user(user.id)["points"] < LIKE_COST:
            context.user_data.clear()
            return await msg.reply_text("🪙 Not enough points. Claim Daily Bonus or redeem a code.", reply_markup=MAIN_KB)
        target = context.user_data["target_uid"]
        await msg.reply_text(
            "📡 <b>LIKE REQUEST PROCESSING</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 UID: <code>{escape(target)}</code>\n"
            f"🌍 Region: <b>{escape(region)}</b>\n"
            "⏳ Status: Contacting Like API…\n\n"
            "Please wait for the verified result.",
            parse_mode=ParseMode.HTML, reply_markup=MAIN_KB)
        try:
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{LIKE_API_URL}/like", params={"uid": target, "server_name": region}) as resp:
                    http_status = resp.status
                    try: data = await resp.json(content_type=None)
                    except Exception: data = {"message": (await resp.text())[:500]}
            ok = http_status < 400 and isinstance(data, dict) and data.get("status") == 1
            with db() as con:
                con.execute("INSERT INTO requests(user_id,uid,region,status,result,created_at) VALUES(?,?,?,?,?,?)",
                            (user.id, target, region, "SUCCESS" if ok else "FAILED", str(data)[:1500], int(time.time())))
                if ok and LIKE_COST:
                    con.execute("UPDATE users SET points=points-? WHERE user_id=? AND points>=?", (LIKE_COST, user.id, LIKE_COST))
            context.user_data.clear()
            if ok:
                await msg.reply_text(
                    f"✅ <b>LIKE REQUEST SUCCESS</b>\n\n"
                    f"👤 Player: {escape(str(data.get('PlayerNickname','Unknown')))}\n"
                    f"🆔 UID: <code>{escape(target)}</code>\n🌍 Region: {escape(region)}\n"
                    f"❤️ Likes added: <b>{escape(str(data.get('LikesGivenByAPI','Unknown')))}</b>\n"
                    f"📉 Before: {escape(str(data.get('LikesbeforeCommand','?')))}\n"
                    f"📈 After: {escape(str(data.get('LikesafterCommand','?')))}\n"
                    f"🪙 Points used: {LIKE_COST}\n"
                    f"💳 Remaining points: {get_user(user.id)['points']}",
                    parse_mode=ParseMode.HTML, reply_markup=MAIN_KB)
            else:
                await msg.reply_text(
                    "⚠️ <b>LIKE REQUEST NOT CONFIRMED</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n\n"
                    f"🆔 UID: <code>{escape(target)}</code>\n"
                    f"🌍 Region: <b>{escape(region)}</b>\n"
                    "❌ The API did not confirm a successful like request.\n\n"
                    f"<code>{escape(str(data)[:700])}</code>\n\n"
                    "🪙 No points were charged.",
                    parse_mode=ParseMode.HTML, reply_markup=MAIN_KB)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning("API request failed: %s", e)
            context.user_data.clear()
            await msg.reply_text("❌ Could not connect to the Like API. No points were charged.", reply_markup=MAIN_KB)
        return
    if flow == "redeem":
        context.user_data.clear(); return await redeem(update, text)
    if flow == "admin_points":
        if not is_admin(user.id): context.user_data.clear(); return
        parts = text.split()
        if len(parts) != 2 or not parts[0].isdigit(): return await msg.reply_text("Format: USER_ID AMOUNT")
        target, amount = int(parts[0]), int(parts[1])
        with db() as con:
            row = con.execute("SELECT points FROM users WHERE user_id=?", (target,)).fetchone()
            if not row: return await msg.reply_text("User not found.")
            if row["points"] + amount < 0: return await msg.reply_text("Balance cannot be negative.")
            con.execute("UPDATE users SET points=points+? WHERE user_id=?", (amount, target))
            balance = row["points"] + amount
        context.user_data.clear()
        return await msg.reply_text(f"✅ Updated. New balance: {balance}", reply_markup=ADMIN_KB)
    if flow == "admin_code":
        if not is_admin(user.id): context.user_data.clear(); return
        parts = text.split()
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
            return await msg.reply_text("Format: CODE POINTS MAX_USES")
        code, points, limit = parts[0].upper(), int(parts[1]), int(parts[2])
        if points < 1 or limit < 1 or len(code) > 40: return await msg.reply_text("Points and max uses must be positive.")
        try:
            with db() as con:
                con.execute("INSERT INTO redeem_codes(code,points,max_uses,created_by,created_at) VALUES(?,?,?,?,?)",
                            (code, points, limit, user.id, int(time.time())))
        except sqlite3.IntegrityError:
            return await msg.reply_text("Code already exists.")
        context.user_data.clear()
        return await msg.reply_text(f"✅ Created {code}: {points} points, {limit} uses.", reply_markup=ADMIN_KB)
    if flow == "admin_broadcast":
        if not is_admin(user.id): context.user_data.clear(); return
        context.user_data.clear()
        with db() as con: ids = [r["user_id"] for r in con.execute("SELECT user_id FROM users").fetchall()]
        sent = 0
        for target in ids:
            try:
                await context.bot.send_message(chat_id=target, text=text); sent += 1
                await asyncio.sleep(0.05)
            except Exception: pass
        return await msg.reply_text(f"📢 Broadcast sent to {sent}/{len(ids)} users.", reply_markup=ADMIN_KB)

    actions = {
        "❤️  Send Likes": send_likes, "👤  My Profile": profile,
        "🎁  Daily Bonus": daily_bonus, "🎟️  Redeem Code": redeem_start,
        "🏆  Leaderboard": leaderboard, "📊  Statistics": stats,
        "ℹ️  Help": help_cmd, "👥  Total Users": admin_users,
        "🪙  Manage Points": admin_points_start, "🎟️  Create Redeem Code": create_code_start,
        "📢  Broadcast": broadcast_start,
    }
    if text in actions: return await actions[text](update, context)
    await msg.reply_text("Choose an option from the menu, or send /help.", reply_markup=MAIN_KB)

def main():
    if not BOT_TOKEN: raise SystemExit("BOT_TOKEN missing. Set it in your host environment.")
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    log.info("FAST LIKE Bot starting; API configured=%s", bool(LIKE_API_URL))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
