"""
╔══════════════════════════════════════════════════╗
║          LIFE RPG — Telegram Bot                 ║
║  Звания: Нулячий пассажир → Киборг × вечность   ║
╚══════════════════════════════════════════════════╝

Установка:  pip install python-telegram-bot
Запуск:     python3 bot.py
"""

import json, os, random, logging, asyncio, sys
from aiohttp import web
from datetime import date, timedelta, datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
if not BOT_TOKEN:
    print("❌ Нет BOT_TOKEN! Добавь переменную окружения.")
    sys.exit(1)
DATA_FILE = "data.json"
MINI_APP_URL = "https://life-rpg-miniapp.vercel.app"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

WORK, MEALS, SLEEP, STEPS, WORKOUT, BOOK, ALCOHOL = range(7)

PHILOSOPHY = [
    "🧠 «Если ты не записал — значит этого не было. А значит, ты весь день просто дышал.»",
    "🌊 «Вода не спрашивает, удобно ли камню. Вода просто мокрая. Будь водой, записывай данные.»",
    "🪨 «Великая стена начиналась с одного кирпича. Ты пока даже не нашёл кирпич. Начни с /log.»",
    "🐢 «Черепаха победила зайца не потому что была быстрой. А потому что заяц не вёл статистику.»",
    "🌅 «Каждое утро — новый шанс. Каждый вечер — старый шанс, который ты уже про*рал. Не про*ри этот.»",
    "🔮 «Будущее туманно. Но твои вчерашние шаги — конкретная цифра. Введи её.»",
    "🦆 «Утка каждый день делает одно и то же. Утка счастлива. Думай об этом.»",
    "⚖️ «Сенека говорил: не трать время впустую. Сенека не знал про /log, но явно имел это в виду.»",
    "🏔️ «Эверест покоряют не прыжком. Его покоряют скучными маленькими шагами. Сколько у тебя было вчера?»",
    "🤖 «Киборг помноженный на вечность не рождается. Он формируется одной строчкой данных в день.»",
]

RANKS = [
    {"minXP": 0,    "emoji": "🪣", "title": "Нулячий пассажир",             "sub": "Просто существует. Диван его дом."},
    {"minXP": 550,  "emoji": "🌱", "title": "Подающий надежды",              "sub": "Старается. Иногда. Почти."},
    {"minXP": 1100, "emoji": "😎", "title": "Нормис",                        "sub": "Уже что-то есть. Люди замечают."},
    {"minXP": 1650, "emoji": "👔", "title": "Почти Дуров",                   "sub": "Режим есть. Телеграм читает стоя."},
    {"minXP": 2200, "emoji": "🤖", "title": "Киборг помноженный на вечность","sub": "Не человек. Легенда. Протокол."},
]

RANK_IMAGES = {
    "Нулячий пассажир":               "avatar_1.jpg",
    "Подающий надежды":               "avatar_2.jpg",
    "Нормис":                         "avatar_3.jpg",
    "Почти Дуров":                    "avatar_4.jpg",
    "Киборг помноженный на вечность": "avatar_5.jpg",
}

def get_rank(xp):
    for r in reversed(RANKS):
        if xp >= r["minXP"]: return r
    return RANKS[0]

def get_next_rank(xp):
    for r in RANKS:
        if r["minXP"] > xp: return r
    return None

def is_weekend():
    return date.today().weekday() >= 5

def score_work(h):    return 30 if h >= 6 else 20 if h >= 4 else 8 if h >= 2 else 0
def score_meals(m):   return 25 if m >= 5 else 20 if m == 4 else 10 if m == 3 else 5 if m == 2 else 0
def score_sleep(h):   return 25 if h >= 8 else 20 if h >= 7 else 10 if h >= 6 else 3 if h >= 5 else 0
def score_steps(s):   return 20 if s >= 10000 else 15 if s >= 5000 else 6 if s >= 2500 else 0
def score_workout(w): return 15 if w else 0
def score_book(p):    return min(50, (int(p) // 50) * 10)
def score_alcohol(a): return -40 if a else 0
def streak_mult(s):   return 1.5 if s >= 14 else 1.3 if s >= 7 else 1.15 if s >= 3 else 1.0

def calc_day(entry, streak, weekend):
    work_pts = 0 if weekend else score_work(entry.get("work", 0))
    base = (work_pts + score_meals(entry.get("meals", 0))
            + score_sleep(entry.get("sleep", 0)) + score_steps(entry.get("steps", 0))
            + score_workout(entry.get("workout", False)) + score_book(entry.get("book", 0)))
    mult    = streak_mult(streak)
    alcohol = score_alcohol(entry.get("alcohol", False))
    total   = max(0, round(base * mult) + alcohol)
    return total, base, mult, alcohol

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(data, uid):
    if uid not in data:
        data[uid] = {"xp": 0, "streak": 0, "last_log": None, "history": []}
    return data[uid]

def weekly_workout_count(history):
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    return sum(1 for d in history if d.get("date", "") >= week_ago and d.get("workout"))

def xp_bar(xp):
    rank = get_rank(xp)
    nxt  = get_next_rank(xp)
    if not nxt: return "▓▓▓▓▓▓▓▓▓▓ 👑 MAX"
    filled = int(((xp - rank["minXP"]) / (nxt["minXP"] - rank["minXP"])) * 10)
    return "▓" * filled + "░" * (10 - filled) + f" {nxt['minXP'] - xp} XP до {nxt['emoji']}"

def app_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Открыть приложение", web_app=WebAppInfo(url=MINI_APP_URL))]])

async def send_avatar(context, chat_id, rank, text, reply_markup=None):
    img = RANK_IMAGES.get(rank["title"])
    if img and os.path.exists(img):
        with open(img, "rb") as f:
            await context.bot.send_photo(chat_id=chat_id, photo=f, caption=text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=reply_markup)

async def cmd_start(update, context):
    uid  = str(update.effective_user.id)
    data = load_data(); user = get_user(data, uid); save_data(data)
    rank = get_rank(user["xp"])
    text = (f"Привет! Я <b>Life RPG Bot</b> 🎮\n\nЗвание: {rank['emoji']} <b>{rank['title']}</b>\n"
            f"XP: <b>{user['xp']}</b>\n\nКаждый день в 10:00 буду напоминать внести данные за вчера.\n\n"
            f"/log — внести · /status — прогресс · /week — неделя · /help — правила")
    await send_avatar(context, update.effective_chat.id, rank, text, app_keyboard())

async def cmd_status(update, context):
    uid  = str(update.effective_user.id)
    data = load_data(); user = get_user(data, uid)
    rank = get_rank(user["xp"]); nxt = get_next_rank(user["xp"])
    wk = weekly_workout_count(user["history"])
    text = (f"{rank['emoji']} <b>{rank['title']}</b>\n<i>{rank['sub']}</i>\n\n"
            f"⚡️ XP: <b>{user['xp']}</b>\n🔥 Streak: <b>{user['streak']} дней</b>\n"
            f"🏋️ Тренировки недели: <b>{wk}/3</b>\n\n{xp_bar(user['xp'])}")
    if nxt: text += f"\n\nДо <b>{nxt['emoji']} {nxt['title']}</b>: <b>{nxt['minXP'] - user['xp']} XP</b>"
    await send_avatar(context, update.effective_chat.id, rank, text, app_keyboard())

async def cmd_week(update, context):
    uid  = str(update.effective_user.id)
    data = load_data(); user = get_user(data, uid)
    hist = user["history"][-7:]
    if not hist:
        await update.message.reply_text("Пока нет данных. Начни с /log!"); return
    wk_count = weekly_workout_count(user["history"])
    wk_bonus = 50 if wk_count >= 3 else 0
    chart = ""
    for d in hist:
        bars = max(1, min(8, int((d["xp"] / 130) * 8)))
        chart += "▓"*bars + "░"*(8-bars) + f" {d['xp']} XP"
        chart += " 🏋️" if d.get("workout") else ""
        chart += " 📚" if d.get("book", 0) >= 50 else ""
        chart += " 🍺" if d.get("alcohol") else ""
        chart += "\n"
    alcohol_days = sum(1 for d in hist if d.get("alcohol"))
    text = (f"📊 <b>Итоги недели</b>\n\n<pre>{chart}</pre>"
            f"⚡️ Всего XP: <b>{sum(d['xp'] for d in hist)}</b>\n"
            f"🏋️ Тренировки: <b>{wk_count}/3</b>" + (f" 🏆 +{wk_bonus} XP!" if wk_bonus else "") + "\n"
            f"😴 Средний сон: <b>{sum(d['sleep'] for d in hist)/len(hist):.1f}ч</b>\n"
            f"👟 Средние шаги: <b>{int(sum(d.get('steps',0) for d in hist)/len(hist)):,}</b>\n"
            f"📚 Страниц: <b>{sum(d.get('book',0) for d in hist)}</b>\n"
            f"🍺 Дней с алкоголем: <b>{alcohol_days}</b> " + ("✅" if alcohol_days <= 1 else "⚠️"))
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_help(update, context):
    await update.message.reply_text(
        "📖 <b>Система очков</b>\n\n"
        "💼 Работа (пн–пт): 4ч=+20, 6ч+=+30\n"
        "🍽 Еда: 4 приёма=+20, 5+=+25\n"
        "😴 Сон: 7–8ч=+20, 8ч+=+25\n"
        "👟 Шаги: 5000=+15, 10000+=+20\n"
        "🏋️ Тренировка: +15 (цель 3/нед)\n"
        "📚 Книга: каждые 50 стр = +10 (макс +50)\n"
        "🍺 Алкоголь: −40 XP\n\n"
        "🔥 Streak: 3д=×1.15 · 7д=×1.3 · 14д=×1.5\n\n"
        "🪣 0 — Нулячий пассажир\n"
        "🌱 550 — Подающий надежды\n"
        "😎 1100 — Нормис\n"
        "👔 1650 — Почти Дуров\n"
        "🤖 2200 — Киборг помноженный на вечность",
        parse_mode="HTML"
    )

async def cmd_log(update, context):
    uid = str(update.effective_user.id)
    data = load_data(); user = get_user(data, uid)
    today = date.today().isoformat()
    if user.get("last_log") == today:
        await update.message.reply_text("✅ Данные уже внесены сегодня!\n/status — посмотреть прогресс")
        return ConversationHandler.END
    context.user_data["log"] = {}
    context.user_data["weekend"] = is_weekend()
    if context.user_data["weekend"]:
        await update.message.reply_text(
            "🛋 <b>Выходной — работу не считаем!</b>\n\n"
            "🍽 <b>Шаг 1 — Приёмы пищи</b>\n\nСколько раз поел вчера?\n<i>4 = норма · 5+ = перевыполнение</i>",
            parse_mode="HTML"); return MEALS
    await update.message.reply_text(
        "💼 <b>Шаг 1/7 — Работа</b>\n\nСколько часов работал вчера?\n<i>4ч = норма · 6ч+ = огонь</i>",
        parse_mode="HTML"); return WORK

async def got_work(update, context):
    try:
        val = float(update.message.text.replace(",", "."))
        assert 0 <= val <= 20
    except:
        await update.message.reply_text("Напиши число от 0 до 20 👆"); return WORK
    context.user_data["log"]["work"] = val
    await update.message.reply_text(
        f"✅ Работа {val}ч → <b>+{score_work(val)} XP</b>\n\n"
        f"🍽 <b>Шаг 2/7 — Приёмы пищи</b>\n\nСколько раз поел вчера?\n<i>4 = норма · 5+ = перевыполнение</i>",
        parse_mode="HTML"); return MEALS

async def got_meals(update, context):
    try:
        val = int(update.message.text.strip()); assert 0 <= val <= 15
    except:
        await update.message.reply_text("Напиши число от 0 до 15 👆"); return MEALS
    context.user_data["log"]["meals"] = val
    s = 2 if context.user_data["weekend"] else 3
    await update.message.reply_text(
        f"✅ Еда {val} раз → <b>+{score_meals(val)} XP</b>\n\n"
        f"😴 <b>Шаг {s}/7 — Сон</b>\n\nСколько часов спал прошлой ночью?\n<i>7–8ч = норма · 8ч+ = идеал</i>",
        parse_mode="HTML"); return SLEEP

async def got_sleep(update, context):
    try:
        val = float(update.message.text.replace(",", ".")); assert 0 <= val <= 16
    except:
        await update.message.reply_text("Напиши число от 0 до 16 👆"); return SLEEP
    context.user_data["log"]["sleep"] = val
    s = 3 if context.user_data["weekend"] else 4
    await update.message.reply_text(
        f"✅ Сон {val}ч → <b>+{score_sleep(val)} XP</b>\n\n"
        f"👟 <b>Шаг {s}/7 — Шаги</b>\n\nСколько шагов сделал вчера?\n<i>5 000 = норма · 10 000+ = красавчик</i>",
        parse_mode="HTML"); return STEPS

async def got_steps(update, context):
    try:
        val = int(update.message.text.strip().replace(" ","").replace(",","")); assert 0 <= val <= 100000
    except:
        await update.message.reply_text("Напиши число шагов (например: 7500) 👆"); return STEPS
    context.user_data["log"]["steps"] = val
    s = 4 if context.user_data["weekend"] else 5
    kb = [[InlineKeyboardButton("✅ Да!", callback_data="workout_yes"),
           InlineKeyboardButton("❌ Нет", callback_data="workout_no")]]
    await update.message.reply_text(
        f"✅ Шаги {val:,} → <b>+{score_steps(val)} XP</b>\n\n"
        f"🏋️ <b>Шаг {s}/7 — Тренировка</b>\n\nБыла тренировка вчера?\n<i>Цель: 3/нед · +15 XP</i>",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb)); return WORKOUT

async def got_workout(update, context):
    q = update.callback_query; await q.answer()
    workout = q.data == "workout_yes"
    context.user_data["log"]["workout"] = workout
    s = 5 if context.user_data["weekend"] else 6
    await q.message.reply_text(
        f"{'✅ +15 XP' if workout else '❌ Без тренировки'}\n\n"
        f"📚 <b>Шаг {s}/7 — Книга</b>\n\nСколько страниц прочитал вчера?\n<i>каждые 50 стр = +10 XP · 0 если не читал</i>",
        parse_mode="HTML"); return BOOK

async def got_book(update, context):
    try:
        val = int(update.message.text.strip()); assert 0 <= val <= 1000
    except:
        await update.message.reply_text("Напиши число страниц (или 0) 👆"); return BOOK
    context.user_data["log"]["book"] = val
    pts = score_book(val)
    s = 6 if context.user_data["weekend"] else 7
    kb = [[InlineKeyboardButton("🍺 Да, грешен", callback_data="alcohol_yes"),
           InlineKeyboardButton("✅ Нет, чист",  callback_data="alcohol_no")]]
    book_text = f"{val} стр → <b>+{pts} XP</b>" if val > 0 else "не читал"
    await update.message.reply_text(
        f"✅ Книга: {book_text}\n\n"
        f"🍺 <b>Шаг {s}/7 — Алкоголь</b>\n\nБыл алкоголь вчера?\n<i>Честно. Никто не смотрит. Ну почти.</i>",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb)); return ALCOHOL

async def got_alcohol(update, context):
    q = update.callback_query; await q.answer()
    alcohol = q.data == "alcohol_yes"
    context.user_data["log"]["alcohol"] = alcohol

    uid  = str(q.from_user.id)
    data = load_data(); user = get_user(data, uid)
    entry   = context.user_data["log"]
    weekend = context.user_data["weekend"]
    today   = date.today().isoformat()

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    if user.get("last_log") == yesterday: user["streak"] += 1
    elif user.get("last_log") != today:   user["streak"] = 1

    total, base, mult, alc_pts = calc_day(entry, user["streak"], weekend)

    wk_count = weekly_workout_count(user["history"])
    wk_bonus = 50 if (entry.get("workout") and wk_count == 2) else 0

    old_rank = get_rank(user["xp"])
    user["xp"] = max(0, user["xp"] + total + wk_bonus)
    user["last_log"] = today
    entry.update({"xp": total, "date": today})
    user["history"].append(entry)
    new_rank = get_rank(user["xp"])
    save_data(data)

    work_line = "" if weekend else f"💼 Работа {entry.get('work',0)}ч → +{score_work(entry.get('work',0))}\n"
    text = (
        f"{'🍺 Грешен' if alcohol else '✅ Чист'}\n\n📊 <b>Итог дня:</b>\n"
        f"{work_line}"
        f"🍽 Еда {entry['meals']} раз → +{score_meals(entry['meals'])}\n"
        f"😴 Сон {entry['sleep']}ч → +{score_sleep(entry['sleep'])}\n"
        f"👟 Шаги {entry['steps']:,} → +{score_steps(entry['steps'])}\n"
        f"🏋️ Тренировка → +{score_workout(entry['workout'])}\n"
        f"📚 Книга {entry.get('book',0)} стр → +{score_book(entry.get('book',0))}\n"
        f"🍺 Алкоголь → {alc_pts}\n"
    )
    if mult > 1: text += f"🔥 Streak {user['streak']}д ×{mult} → +{round(base*mult)-base}\n"
    if wk_bonus: text += f"🏆 3 тренировки! → +{wk_bonus}\n"
    text += f"\n⚡️ <b>+{total+wk_bonus} XP</b>\nВсего: <b>{user['xp']} XP</b>\n\n{xp_bar(user['xp'])}"

    if new_rank["title"] != old_rank["title"]:
        text = f"🎉🎉🎉 <b>НОВОЕ ЗВАНИЕ!</b>\n\n{new_rank['emoji']} <b>{new_rank['title']}</b>\n<i>{new_rank['sub']}</i>\n\n" + text
        await send_avatar(context, q.message.chat_id, new_rank, text)
    else:
        await q.message.reply_text(text, parse_mode="HTML")
    return ConversationHandler.END

async def cancel(update, context):
    await update.message.reply_text("Отменено. /log — когда будешь готов")
    return ConversationHandler.END

# ── УВЕДОМЛЕНИЯ ───────────────────────────────────────────────
async def morning_reminder(context):
    """10:00 каждый день — напоминание с тупой философией"""
    data  = load_data()
    today = date.today().isoformat()
    quote = random.choice(PHILOSOPHY)
    for uid, user in data.items():
        if user.get("last_log") == today: continue
        rank = get_rank(user["xp"])
        wd_note = " Сегодня выходной, работу не считаем 🛋" if date.today().weekday() >= 5 else ""
        text = (f"☀️ Доброе утро, {rank['emoji']} <b>{rank['title']}</b>!\n\n"
                f"Пора внести данные за вчера.{wd_note}\n\n{quote}\n\n→ /log")
        try:
            await context.bot.send_message(chat_id=int(uid), text=text, parse_mode="HTML")
        except Exception as e:
            log.warning(f"Не смог отправить {uid}: {e}")

async def weekly_summary(context):
    """Воскресенье 20:00 — итоги недели"""
    data = load_data()
    for uid, user in data.items():
        hist = user["history"][-7:]
        if not hist: continue
        wk = weekly_workout_count(user["history"])
        rank = get_rank(user["xp"])
        wk_bonus = 50 if wk >= 3 else 0
        if wk_bonus:
            user["xp"] += wk_bonus
            save_data(data)
        text = (f"📅 <b>Итоги недели!</b>\n\n{rank['emoji']} {rank['title']}\n"
                f"⚡️ XP за неделю: <b>{sum(d['xp'] for d in hist)}</b>\n"
                f"🏋️ Тренировки: <b>{wk}/3</b>"
                + (f"\n🏆 +{wk_bonus} XP бонус!" if wk_bonus else "")
                + "\n\nНовая неделя — новый шанс. /log")
        try:
            await send_avatar(context, int(uid), rank, text)
        except: pass


# ── API SERVER для Mini App ───────────────────────────────────
async def handle_get_user(request):
    """Mini App запрашивает данные пользователя"""
    uid = request.rel_url.query.get("uid")
    if not uid:
        return web.json_response({"error": "no uid"}, status=400)
    data = load_data()
    user = get_user(data, uid)
    rank = get_rank(user["xp"])
    nxt  = get_next_rank(user["xp"])
    return web.json_response({
        "xp":      user["xp"],
        "streak":  user["streak"],
        "history": user["history"][-10:],
        "rank":    rank["title"],
        "nextRank": nxt["title"] if nxt else None,
        "lastLog": user.get("last_log"),
    })

async def handle_save_log(request):
    """Mini App отправляет данные после заполнения"""
    try:
        body = await request.json()
    except:
        return web.json_response({"error": "invalid json"}, status=400)

    uid     = body.get("uid")
    answers = body.get("answers", {})
    weekend = body.get("weekend", False)

    if not uid:
        return web.json_response({"error": "no uid"}, status=400)

    data = load_data()
    user = get_user(data, uid)
    today = date.today().isoformat()

    if user.get("last_log") == today:
        return web.json_response({"error": "already logged today"}, status=400)

    # Update streak
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    if user.get("last_log") == yesterday: user["streak"] += 1
    elif user.get("last_log") != today:   user["streak"] = 1

    total, base, mult, alc_pts = calc_day(answers, user["streak"], weekend)

    # Weekly workout bonus
    wk_count = weekly_workout_count(user["history"])
    wk_bonus = 50 if (answers.get("workout") and wk_count == 2) else 0

    old_rank = get_rank(user["xp"])
    user["xp"] = max(0, user["xp"] + total + wk_bonus)
    user["last_log"] = today
    answers.update({"xp": total, "date": today})
    user["history"].append(answers)
    new_rank = get_rank(user["xp"])
    save_data(data)

    rank_up = new_rank["title"] != old_rank["title"]

    return web.json_response({
        "xp":      user["xp"],
        "streak":  user["streak"],
        "earned":  total + wk_bonus,
        "wkBonus": wk_bonus,
        "rankUp":  rank_up,
        "newRank": new_rank["title"] if rank_up else None,
    })

async def start_api_server():
    app_api = web.Application()
    app_api.router.add_get("/user", handle_get_user)
    app_api.router.add_post("/log", handle_save_log)
    runner = web.AppRunner(app_api)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080)))
    await site.start()
    print(f"🌐 API сервер запущен на порту {os.environ.get('PORT', 8080)}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("log", cmd_log)],
        states={
            WORK:    [MessageHandler(filters.TEXT & ~filters.COMMAND, got_work)],
            MEALS:   [MessageHandler(filters.TEXT & ~filters.COMMAND, got_meals)],
            SLEEP:   [MessageHandler(filters.TEXT & ~filters.COMMAND, got_sleep)],
            STEPS:   [MessageHandler(filters.TEXT & ~filters.COMMAND, got_steps)],
            WORKOUT: [CallbackQueryHandler(got_workout,  pattern="^workout_")],
            BOOK:    [MessageHandler(filters.TEXT & ~filters.COMMAND, got_book)],
            ALCOHOL: [CallbackQueryHandler(got_alcohol,  pattern="^alcohol_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("week",   cmd_week))
    app.add_handler(CommandHandler("help",   cmd_help))

    # Запускаем планировщик через asyncio
    async def run():
        await start_api_server()
        async with app:
            await app.start()
            await app.updater.start_polling()
            asyncio.create_task(scheduler_loop(app))
            print("🤖 Life RPG Bot запущен!")
            await asyncio.Event().wait()

    asyncio.run(run())


async def scheduler_loop(app):
    """Проверяет время каждую минуту и запускает задачи"""
    while True:
        now = datetime.now()
        # Утреннее уведомление в 10:00
        if now.hour == 10 and now.minute == 0:
            await morning_reminder(app)
        # Итоги недели — воскресенье в 20:00
        if now.weekday() == 6 and now.hour == 20 and now.minute == 0:
            await weekly_summary(app)
        await asyncio.sleep(60)  # проверяем раз в минуту

if __name__ == "__main__":
    main()
