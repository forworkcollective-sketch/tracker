"""
ФОКУС-ТРЕКЕР v2 — Telegram Bot
python-telegram-bot (v20+), async handlers, Moscow timezone
"""
import logging
from datetime import date, datetime, time as dtime, timezone, timedelta

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, WebAppInfo,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters,
)
from telegram.constants import ParseMode

from config import BOT_TOKEN, OWNER_ID, DAILY_BUDGET_MINUTES, WEB_PORT
import db
import motivation
import autotasks

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bot")

MSK = timezone(timedelta(hours=3))
WEBAPP_URL = f"http://localhost:{WEB_PORT}"
POMODORO_MIN = 30


# ═══════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════

def fmt_minutes(mins: float) -> str:
    mins = round(mins)
    h, m = divmod(mins, 60)
    if h and m:
        return f"{h}ч {m}мин"
    if h:
        return f"{h}ч"
    return f"{m}мин"


def progress_bar(current: float, total: float, length: int = 10) -> str:
    if total <= 0:
        return "░" * length
    filled = int(round(current / total * length))
    filled = min(filled, length)
    return "▓" * filled + "░" * (length - filled)


def fmt_rub(n: float) -> str:
    n = int(round(n))
    s = f"{abs(n):,}".replace(",", " ")
    return f"{'-' if n < 0 else ''}{s}₽"


def is_owner(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == OWNER_ID


def today_str() -> str:
    return date.today().isoformat()


# ═══════════════════════════════════════════
# PERSISTENT REPLY KEYBOARD
# ═══════════════════════════════════════════

MAIN_KB = ReplyKeyboardMarkup(
    [
        ["📋 План", "▶ Фокус", "✅ Готово"],
        ["🎁 Награды", "🎯 Цели", "💰 Долги"],
        ["📈 Продажи", "📊 Статы"],
    ],
    resize_keyboard=True,
)


# ═══════════════════════════════════════════
# BUILD DEBTS INLINE (no web.py dependency)
# ═══════════════════════════════════════════

def build_debts():
    debts = db.get_all_financial_goals()
    total_target = sum(d.get("target_rub") or 0 for d in debts)
    total_paid = sum(d.get("paid_rub") or 0 for d in debts)
    for d in debts:
        t = d.get("target_rub") or 0
        p = d.get("paid_rub") or 0
        d["pct"] = int(p / t * 100) if t > 0 else 0
        d["remaining"] = max(t - p, 0)
    return {
        "items": debts,
        "total_target": total_target,
        "total_paid": total_paid,
        "total_remaining": max(total_target - total_paid, 0),
        "pct": int(total_paid / total_target * 100) if total_target > 0 else 0,
    }


# ═══════════════════════════════════════════
# COMMAND: /start
# ═══════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return await update.message.reply_text("Бот только для владельца.")

    mins = db.get_today_minutes()
    streak = db.get_streak()
    xp = db.get_xp()
    pomos = db.get_today_pomodoros()

    text = (
        "Привет! Я — Фокус-Трекер.\n\n"
        f"Сегодня: {fmt_minutes(mins)} / {fmt_minutes(DAILY_BUDGET_MINUTES)}\n"
        f"{progress_bar(mins, DAILY_BUDGET_MINUTES)} {int(mins / max(DAILY_BUDGET_MINUTES, 1) * 100)}%\n\n"
        f"🍅 Помодорок: {pomos}/8\n"
        f"🔥 Стрик: {streak} дн.\n"
        f"⭐ XP: {xp['total_xp']} (ур. {xp['level']})\n\n"
        "Жми /plan чтобы увидеть план дня."
    )
    await update.message.reply_text(text, reply_markup=MAIN_KB)


# ═══════════════════════════════════════════
# COMMAND: /plan
# ═══════════════════════════════════════════

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    tasks = db.get_tasks_for_date(today_str())
    mins = db.get_today_minutes()
    schedule = db.get_today_schedule()
    active = db.get_active_timer()

    focus_text = schedule.get("focus", "Свободный день")
    weekday_idx = date.today().weekday()
    day_name = db.DAYS_RU[weekday_idx]

    lines = [f"📋 <b>План на сегодня</b> ({day_name} — {focus_text})"]
    lines.append(f"⏱ {fmt_minutes(mins)} / {fmt_minutes(DAILY_BUDGET_MINUTES)}  {progress_bar(mins, DAILY_BUDGET_MINUTES)}")
    lines.append("")

    if not tasks:
        lines.append("Задач пока нет. Жми «Сгенерировать план» или /add")
        kb = [[InlineKeyboardButton("🤖 Сгенерировать план", callback_data="autoplan")]]
    else:
        kb = []
        for i, t in enumerate(tasks, 1):
            emoji = t.get("goal_emoji", "🎯")
            status_icon = "✅" if t["status"] == "done" else ("⏳" if t["status"] == "in_progress" else "⬜")
            lines.append(
                f"{status_icon} {emoji} <b>{t['title']}</b> ({fmt_minutes(t['estimate_min'])})"
            )
            if t["status"] not in ("done",):
                kb.append([InlineKeyboardButton(
                    f"▶ {t['title'][:30]}",
                    callback_data=f"start_{t['id']}"
                )])

        est_total = sum(t["estimate_min"] for t in tasks)
        done_count = sum(1 for t in tasks if t["status"] == "done")
        lines.append(f"\nИтого: {len(tasks)} задач на ~{fmt_minutes(est_total)} | Выполнено: {done_count}")

    if active:
        lines.append(f"\n🔴 Сейчас: {active['task_title']}")

    kb.append([InlineKeyboardButton("✏ Открыть WebApp", web_app=WebAppInfo(url=WEBAPP_URL))])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


# ═══════════════════════════════════════════
# COMMAND: /focus — start pomodoro
# ═══════════════════════════════════════════

async def cmd_focus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    # Check if already running
    active = db.get_active_timer()
    if active:
        started = datetime.fromisoformat(active["started_at"])
        elapsed = (datetime.now() - started).total_seconds() / 60
        await update.message.reply_text(
            f"🔴 Таймер уже запущен!\n"
            f"Задача: <b>{active['task_title']}</b>\n"
            f"Прошло: {fmt_minutes(elapsed)}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏹ Остановить", callback_data="stop_timer")],
                [InlineKeyboardButton("✅ Завершить задачу", callback_data=f"done_{active['task_id']}")],
            ]),
        )
        return

    # Budget check
    mins = db.get_today_minutes()
    if mins >= DAILY_BUDGET_MINUTES:
        await update.message.reply_text(
            f"🎉 Ты уже отработал {fmt_minutes(mins)} сегодня!\n"
            "Бюджет на сегодня выполнен. Отдохни!"
        )
        return

    # Show task picker
    tasks = db.get_tasks_for_date(today_str())
    todo = [t for t in tasks if t["status"] in ("todo", "in_progress")]
    if not todo:
        await update.message.reply_text(
            "Нет запланированных задач. Используй /plan или /add"
        )
        return

    kb = []
    for t in todo:
        emoji = t.get("goal_emoji", "🎯")
        kb.append([InlineKeyboardButton(
            f"{emoji} {t['title'][:40]}",
            callback_data=f"start_{t['id']}"
        )])

    await update.message.reply_text(
        "🍅 <b>Выбери задачу для помодорки (30 мин):</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


# ═══════════════════════════════════════════
# COMMAND: /done — complete current task
# ═══════════════════════════════════════════

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    active = db.get_active_timer()
    if not active:
        # Show today's in-progress tasks
        tasks = db.get_tasks_for_date(today_str())
        in_progress = [t for t in tasks if t["status"] == "in_progress"]
        if not in_progress:
            await update.message.reply_text("Нет активных задач. Запусти /focus")
            return
        kb = [[InlineKeyboardButton(
            f"✅ {t['title'][:35]}",
            callback_data=f"done_{t['id']}"
        )] for t in in_progress]
        await update.message.reply_text(
            "Какую задачу завершить?",
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return

    task_id = active["task_id"]
    await _complete_task(update, context, task_id)


async def _complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: int):
    """Complete task + stop timer + award XP"""
    duration = db.stop_active_timer()
    db.complete_task(task_id)
    task = db.get_task(task_id)
    task_title = task["title"] if task else "Задача"

    # XP for task
    xp_earned = db.XP_TASK_DONE
    db.add_xp(db.XP_TASK_DONE, "task_done")

    # XP for pomodoro if duration >= 25min
    if duration >= 25:
        pomo_count = max(int(duration // 30), 1)
        pomo_xp = pomo_count * db.XP_POMODORO
        db.add_xp(pomo_xp, "pomodoro")
        xp_earned += pomo_xp

    # Check bonuses
    bonus = 0
    today_min = db.get_today_minutes()
    if today_min >= DAILY_BUDGET_MINUTES:
        bonus += db.XP_FULL_DAY

    today_tasks = db.get_tasks_for_date(today_str())
    if today_tasks and all(t["status"] == "done" for t in today_tasks):
        bonus += db.XP_ALL_TASKS

    if bonus:
        db.add_xp(bonus, "bonus")
        xp_earned += bonus

    xp = db.get_xp()
    quote = motivation.get_done_quote()

    lines = [
        f"✅ <b>{task_title}</b> — выполнена!",
        f"⏱ Затрачено: {fmt_minutes(duration)}",
        f"⭐ +{xp_earned} XP (всего: {xp['total_xp']}, ур. {xp['level']})",
    ]
    if bonus:
        if today_min >= DAILY_BUDGET_MINUTES:
            lines.append(f"🏆 +{db.XP_FULL_DAY} XP бонус за 4ч!")
        if today_tasks and all(t["status"] == "done" for t in today_tasks):
            lines.append(f"🌟 +{db.XP_ALL_TASKS} XP бонус за все задачи дня!")
    lines.append(f"\n💬 {quote}")

    # Rewards hint
    rewards = db.get_rewards()
    affordable = [r for r in rewards if r["cost_xp"] <= xp["total_xp"]]
    if affordable:
        lines.append(f"\n🎁 Доступно наград: {len(affordable)} — /rewards")

    msg = update.message or update.callback_query.message
    await msg.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KB,
    )

    # Check if 4h reached — instant summary
    if today_min >= DAILY_BUDGET_MINUTES:
        await _send_4h_summary(context, update.effective_chat.id)


async def _send_4h_summary(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Congrats message when 4h reached"""
    mins = db.get_today_minutes()
    pomos = db.get_today_pomodoros()
    streak = db.get_streak()
    xp = db.get_xp()
    tasks = db.get_tasks_for_date(today_str())
    done_count = sum(1 for t in tasks if t["status"] == "done")

    text = (
        "🎉🎉🎉 <b>4 ЧАСА ВЫПОЛНЕНЫ!</b> 🎉🎉🎉\n\n"
        f"⏱ Отработано: {fmt_minutes(mins)}\n"
        f"🍅 Помодорок: {pomos}\n"
        f"✅ Задач: {done_count}/{len(tasks)}\n"
        f"🔥 Стрик: {streak} дн.\n"
        f"⭐ XP: {xp['total_xp']} (ур. {xp['level']})\n\n"
        "Ты — машина. Отдохни и наслаждайся вечером!"
    )
    photo = motivation.get_image("day_complete")
    try:
        await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=text, parse_mode=ParseMode.HTML)
    except Exception:
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)


# ═══════════════════════════════════════════
# COMMAND: /rewards
# ═══════════════════════════════════════════

async def cmd_rewards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    rewards = db.get_rewards()
    xp = db.get_xp()

    lines = [
        f"🎁 <b>Каталог наград</b>",
        f"⭐ Твой баланс: {xp['total_xp']} XP (ур. {xp['level']})\n",
    ]

    kb = []
    if not rewards:
        lines.append("Каталог пуст. Добавь награды через WebApp.")
    else:
        for r in rewards:
            can = "✅" if xp["total_xp"] >= r["cost_xp"] else "🔒"
            lines.append(f"{can} {r.get('emoji', '🎁')} <b>{r['title']}</b> — {r['cost_xp']} XP")
            if xp["total_xp"] >= r["cost_xp"]:
                kb.append([InlineKeyboardButton(
                    f"🎁 Забрать: {r['title'][:30]}",
                    callback_data=f"claim_{r['id']}"
                )])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb) if kb else MAIN_KB,
    )


# ═══════════════════════════════════════════
# COMMAND: /goals
# ═══════════════════════════════════════════

async def cmd_goals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    goals = db.get_goals(goal_type="work")
    lines = ["🎯 <b>Рабочие цели</b>\n"]

    for g in goals:
        prog = db.get_goal_progress(g["id"])
        pct = int(prog["done_tasks"] / max(prog["total_tasks"], 1) * 100)
        emoji = g.get("emoji", "🎯")
        lines.append(
            f"{emoji} <b>{g['title']}</b>\n"
            f"   {progress_bar(prog['done_tasks'], prog['total_tasks'])} {pct}% "
            f"({prog['done_tasks']}/{prog['total_tasks']} задач, {prog['hours_spent']}ч)\n"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KB,
    )


# ═══════════════════════════════════════════
# COMMAND: /debts
# ═══════════════════════════════════════════

async def cmd_debts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    data = build_debts()
    items = data["items"]

    lines = ["💰 <b>Прогресс по долгам</b>\n"]

    if not items:
        lines.append("Долгов нет! Свобода!")
    else:
        for d in items:
            target = d.get("target_rub") or 0
            paid = d.get("paid_rub") or 0
            remaining = d.get("remaining", 0)
            pct = d.get("pct", 0)
            emoji = d.get("emoji", "💳")
            lines.append(
                f"{emoji} <b>{d['title']}</b>\n"
                f"   {progress_bar(paid, target)} {pct}%\n"
                f"   Оплачено: {fmt_rub(paid)} / {fmt_rub(target)} (осталось: {fmt_rub(remaining)})\n"
            )

        lines.append(
            f"<b>ИТОГО:</b> {fmt_rub(data['total_paid'])} / {fmt_rub(data['total_target'])} "
            f"({data['pct']}%) | Осталось: {fmt_rub(data['total_remaining'])}"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KB,
    )


# ═══════════════════════════════════════════
# COMMAND: /sales
# ═══════════════════════════════════════════

async def cmd_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    summary = db.get_sales_summary(30)
    lines = ["📈 <b>Продажи за 30 дней</b>\n"]

    if summary["total_clients"] == 0:
        lines.append("Продаж пока нет.")
    else:
        lines.append(f"Клиентов: {summary['total_clients']}")
        lines.append(f"Выручка: {fmt_rub(summary['total_revenue'])}")
        lines.append(f"Расход: {fmt_rub(summary['total_cost'])}")
        lines.append(f"Маржа: {fmt_rub(summary['total_margin'])}\n")

        for pt, data in summary["by_product"].items():
            name = db.PRODUCT_NAMES.get(pt, pt)
            lines.append(f"  {name}: {data['count']} шт, маржа {fmt_rub(data['margin'])}")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KB,
    )


# ═══════════════════════════════════════════
# COMMAND: /add — conversation to add task
# ═══════════════════════════════════════════

ADD_TITLE, ADD_GOAL = range(2)


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "Введи название задачи:",
        reply_markup=MAIN_KB,
    )
    return ADD_TITLE


async def add_title_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_task_title"] = update.message.text.strip()
    goals = db.get_goals(goal_type="work")
    if not goals:
        # No goals — create task without goal
        task_id = db.add_task(
            goal_id=None,
            title=context.user_data["new_task_title"],
            estimate_min=60,
        )
        db.schedule_task(task_id, today_str())
        await update.message.reply_text(
            f"✅ Задача создана: <b>{context.user_data['new_task_title']}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_KB,
        )
        return ConversationHandler.END

    kb = []
    for g in goals:
        emoji = g.get("emoji", "🎯")
        kb.append([InlineKeyboardButton(
            f"{emoji} {g['title'][:40]}",
            callback_data=f"addgoal_{g['id']}"
        )])
    kb.append([InlineKeyboardButton("Без цели", callback_data="addgoal_0")])

    await update.message.reply_text(
        "К какой цели привязать?",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return ADD_GOAL


async def add_goal_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    goal_id_str = query.data.replace("addgoal_", "")
    goal_id = int(goal_id_str) if goal_id_str != "0" else None
    title = context.user_data.get("new_task_title", "Без названия")

    task_id = db.add_task(goal_id=goal_id, title=title, estimate_min=60)
    db.schedule_task(task_id, today_str())

    goal_name = ""
    if goal_id:
        g = db.get_goal(goal_id)
        if g:
            goal_name = f" → {g.get('emoji', '🎯')} {g['title']}"

    await query.edit_message_text(
        f"✅ Задача создана: <b>{title}</b>{goal_name}\n"
        f"Запланирована на сегодня.",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.", reply_markup=MAIN_KB)
    return ConversationHandler.END


# ═══════════════════════════════════════════
# COMMAND: /stats
# ═══════════════════════════════════════════

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    daily = db.get_daily_stats(30)
    streak = db.get_streak()
    xp = db.get_xp()
    by_goal = db.get_time_by_goal(30)

    total_days = len(daily)
    total_min = sum(d["total_min"] for d in daily)
    avg_min = total_min / max(total_days, 1)
    full_days = sum(1 for d in daily if d["total_min"] >= DAILY_BUDGET_MINUTES)

    lines = [
        "📊 <b>Статистика за 30 дней</b>\n",
        f"📅 Рабочих дней: {total_days}",
        f"⏱ Всего: {fmt_minutes(total_min)}",
        f"📈 Среднее/день: {fmt_minutes(avg_min)}",
        f"🏆 Полных дней (4ч+): {full_days}",
        f"🔥 Текущий стрик: {streak} дн.",
        f"⭐ XP: {xp['total_xp']} (ур. {xp['level']})\n",
        "<b>По целям:</b>",
    ]
    for g in by_goal:
        emoji = g.get("emoji", "🎯")
        lines.append(f"  {emoji} {g['title']}: {fmt_minutes(g['total_min'])}")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KB,
    )


# ═══════════════════════════════════════════
# COMMAND: /schedule
# ═══════════════════════════════════════════

async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    schedule = db.get_schedule()
    today_wd = date.today().weekday()

    lines = ["📅 <b>Расписание недели</b>\n"]
    for s in schedule:
        wd = s.get("weekday", 0)
        day_name = db.DAYS_RU[wd] if wd < len(db.DAYS_RU) else "?"
        marker = " 👈" if wd == today_wd else ""
        hours = s.get("hours", 4)
        lines.append(f"<b>{day_name}</b>: {s.get('focus', '—')} ({hours}ч){marker}")

    if not schedule:
        lines.append("Расписание не настроено. Добавь через WebApp.")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KB,
    )


# ═══════════════════════════════════════════
# CALLBACK QUERIES
# ═══════════════════════════════════════════

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_owner(update):
        await query.answer("Нет доступа")
        return

    data = query.data
    await query.answer()

    # ── Start timer ──
    if data.startswith("start_"):
        task_id = int(data.replace("start_", ""))
        task = db.get_task(task_id)
        if not task:
            await query.edit_message_text("Задача не найдена.")
            return

        # Stop any active timer first
        db.stop_active_timer()
        db.start_timer(task_id)

        emoji = task.get("goal_emoji", "🎯")
        await query.edit_message_text(
            f"🍅 <b>Помодорка запущена!</b>\n\n"
            f"{emoji} {task['title']}\n"
            f"⏱ 30 минут — фокус!\n\n"
            f"Я напомню когда время выйдет.",
            parse_mode=ParseMode.HTML,
        )

    # ── Stop timer ──
    elif data == "stop_timer":
        duration = db.stop_active_timer()
        xp_earned = 0
        if duration >= 25:
            pomo_count = max(int(duration // 30), 1)
            xp_earned = pomo_count * db.XP_POMODORO
            db.add_xp(xp_earned, "pomodoro")

        text = f"⏹ Таймер остановлен. Работа: {fmt_minutes(duration)}"
        if xp_earned:
            text += f"\n⭐ +{xp_earned} XP за помодорку"

        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

    # ── Complete task ──
    elif data.startswith("done_"):
        task_id = int(data.replace("done_", ""))
        duration = db.stop_active_timer()
        db.complete_task(task_id)
        task = db.get_task(task_id)
        task_title = task["title"] if task else "Задача"

        xp_earned = db.XP_TASK_DONE
        db.add_xp(db.XP_TASK_DONE, "task_done")

        if duration >= 25:
            pomo_count = max(int(duration // 30), 1)
            pomo_xp = pomo_count * db.XP_POMODORO
            db.add_xp(pomo_xp, "pomodoro")
            xp_earned += pomo_xp

        bonus = 0
        today_min = db.get_today_minutes()
        if today_min >= DAILY_BUDGET_MINUTES:
            bonus += db.XP_FULL_DAY
        today_tasks = db.get_tasks_for_date(today_str())
        if today_tasks and all(t["status"] == "done" for t in today_tasks):
            bonus += db.XP_ALL_TASKS
        if bonus:
            db.add_xp(bonus, "bonus")
            xp_earned += bonus

        xp = db.get_xp()
        quote = motivation.get_done_quote()

        lines = [
            f"✅ <b>{task_title}</b> — выполнена!",
            f"⏱ Затрачено: {fmt_minutes(duration)}",
            f"⭐ +{xp_earned} XP (всего: {xp['total_xp']}, ур. {xp['level']})",
        ]
        if bonus:
            lines.append(f"🏆 Бонус: +{bonus} XP!")
        lines.append(f"\n💬 {quote}")

        await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML)

        if today_min >= DAILY_BUDGET_MINUTES:
            await _send_4h_summary(context, update.effective_chat.id)

    # ── Claim reward ──
    elif data.startswith("claim_"):
        reward_id = int(data.replace("claim_", ""))
        success, message = db.claim_reward(reward_id)
        xp = db.get_xp()
        if success:
            text = f"🎉 {message}\n⭐ Остаток: {xp['total_xp']} XP"
        else:
            text = f"❌ {message}"
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

    # ── Auto plan ──
    elif data == "autoplan":
        tasks, total = autotasks.generate_daily_plan(DAILY_BUDGET_MINUTES)
        if tasks:
            await query.edit_message_text(
                f"🤖 Сгенерировано {len(tasks)} задач на ~{fmt_minutes(total)}.\n"
                "Жми /plan чтобы увидеть.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await query.edit_message_text("Не удалось подобрать задачи.")

    # ── Pomodoro continue ──
    elif data == "pomo_continue":
        active = db.get_active_timer()
        if active:
            task_id = active["task_id"]
            db.stop_active_timer()
            db.start_timer(task_id)
            task = db.get_task(task_id)
            await query.edit_message_text(
                f"🍅 Продолжаем: <b>{task['title'] if task else '?'}</b>\n⏱ Ещё 30 минут!",
                parse_mode=ParseMode.HTML,
            )
        else:
            await query.edit_message_text("Нет активного таймера. /focus")

    # ── Pomodoro switch task ──
    elif data == "pomo_switch":
        db.stop_active_timer()
        tasks = db.get_tasks_for_date(today_str())
        todo = [t for t in tasks if t["status"] in ("todo", "in_progress")]
        if not todo:
            await query.edit_message_text("Нет задач. /add")
            return
        kb = [[InlineKeyboardButton(
            f"{t.get('goal_emoji', '🎯')} {t['title'][:40]}",
            callback_data=f"start_{t['id']}"
        )] for t in todo]
        await query.edit_message_text(
            "🔄 Выбери задачу:",
            reply_markup=InlineKeyboardMarkup(kb),
        )

    # ── Pomodoro break ──
    elif data == "pomo_break":
        db.stop_active_timer()
        await query.edit_message_text(
            "☕ Перерыв 5 минут. Встань, потянись, попей воды.\n"
            "Потом жми /focus"
        )


# ═══════════════════════════════════════════
# REPLY KEYBOARD HANDLER (text messages)
# ═══════════════════════════════════════════

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    text = update.message.text.strip()
    dispatch = {
        "📋 План": cmd_plan,
        "▶ Фокус": cmd_focus,
        "✅ Готово": cmd_done,
        "🎁 Награды": cmd_rewards,
        "🎯 Цели": cmd_goals,
        "💰 Долги": cmd_debts,
        "📈 Продажи": cmd_sales,
        "📊 Статы": cmd_stats,
    }
    handler_fn = dispatch.get(text)
    if handler_fn:
        await handler_fn(update, context)


# ═══════════════════════════════════════════
# SCHEDULED JOBS
# ═══════════════════════════════════════════

async def morning_plan(context: ContextTypes.DEFAULT_TYPE):
    """08:00 MSK — morning motivation + plan"""
    logger.info("Running morning_plan job")

    schedule = db.get_today_schedule()
    weekday_idx = date.today().weekday()
    day_name = db.DAYS_RU[weekday_idx]
    focus_text = schedule.get("focus", "Свободный день")

    # Auto-generate tasks if none scheduled
    tasks = db.get_tasks_for_date(today_str())
    if not tasks:
        autotasks.generate_daily_plan(DAILY_BUDGET_MINUTES)
        tasks = db.get_tasks_for_date(today_str())

    quote = motivation.get_morning_quote()
    streak = db.get_streak()
    xp = db.get_xp()

    lines = [
        f"☀️ <b>Доброе утро!</b>",
        f"💬 {quote}\n",
        f"📅 {day_name} — {focus_text}",
        f"🔥 Стрик: {streak} дн. | ⭐ XP: {xp['total_xp']}\n",
        f"<b>План на 4 часа:</b>",
    ]
    est_total = 0
    for t in tasks:
        emoji = t.get("goal_emoji", "🎯")
        lines.append(f"  {emoji} {t['title']} ({fmt_minutes(t['estimate_min'])})")
        est_total += t["estimate_min"]
    lines.append(f"\nИтого: ~{fmt_minutes(est_total)}")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶ Начать фокус", callback_data="pomo_switch")],
        [InlineKeyboardButton("✏ Открыть WebApp", web_app=WebAppInfo(url=WEBAPP_URL))],
    ])

    photo = motivation.get_image("morning")
    text = "\n".join(lines)
    try:
        await context.bot.send_photo(
            chat_id=OWNER_ID, photo=photo, caption=text,
            parse_mode=ParseMode.HTML, reply_markup=kb,
        )
    except Exception:
        await context.bot.send_message(
            chat_id=OWNER_ID, text=text,
            parse_mode=ParseMode.HTML, reply_markup=kb,
        )


async def evening_summary(context: ContextTypes.DEFAULT_TYPE):
    """21:00 MSK — daily summary"""
    logger.info("Running evening_summary job")

    summary = db.save_daily_summary()
    mins = summary["focus_minutes"]
    done = summary["tasks_done"]
    total = summary["tasks_total"]
    streak = summary["streak"]
    xp = db.get_xp()

    good_day = mins >= DAILY_BUDGET_MINUTES * 0.75
    quote = motivation.get_evening_quote(good=good_day)

    lines = [
        f"🌙 <b>Итоги дня</b>\n",
        f"⏱ Фокус: {fmt_minutes(mins)} / {fmt_minutes(DAILY_BUDGET_MINUTES)}",
        f"   {progress_bar(mins, DAILY_BUDGET_MINUTES)} {int(mins / max(DAILY_BUDGET_MINUTES, 1) * 100)}%",
        f"✅ Задач: {done}/{total}",
        f"🔥 Стрик: {streak} дн.",
        f"⭐ XP: {xp['total_xp']} (ур. {xp['level']})\n",
    ]

    # Debt progress
    data = build_debts()
    if data["items"]:
        lines.append("<b>Долги:</b>")
        for d in data["items"]:
            target = d.get("target_rub") or 0
            paid = d.get("paid_rub") or 0
            pct = d.get("pct", 0)
            emoji = d.get("emoji", "💳")
            lines.append(f"  {emoji} {d['title']}: {progress_bar(paid, target, 8)} {pct}%")
        lines.append(f"  Всего: {fmt_rub(data['total_paid'])} / {fmt_rub(data['total_target'])}")
        lines.append("")

    lines.append(f"💬 {quote}")

    photo = motivation.get_image("evening")
    text = "\n".join(lines)
    try:
        await context.bot.send_photo(
            chat_id=OWNER_ID, photo=photo, caption=text,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        await context.bot.send_message(
            chat_id=OWNER_ID, text=text,
            parse_mode=ParseMode.HTML,
        )


async def check_pomodoro(context: ContextTypes.DEFAULT_TYPE):
    """Every 30 sec — check if active timer exceeded 30 min"""
    active = db.get_active_timer()
    if not active:
        return

    started = datetime.fromisoformat(active["started_at"])
    elapsed_sec = (datetime.now() - started).total_seconds()
    elapsed_min = elapsed_sec / 60

    # Only notify once per timer crossing 30min mark
    notified_key = f"pomo_notified_{active['id']}"
    if elapsed_min >= POMODORO_MIN and not context.bot_data.get(notified_key):
        context.bot_data[notified_key] = True

        # Award XP for completed pomodoro
        db.add_xp(db.XP_POMODORO, "pomodoro")
        xp = db.get_xp()
        today_min = db.get_today_minutes()

        task_title = active.get("task_title", "Задача")
        text = (
            f"🍅 <b>Помодорка завершена!</b>\n\n"
            f"Задача: {task_title}\n"
            f"⏱ {fmt_minutes(elapsed_min)}\n"
            f"⭐ +{db.XP_POMODORO} XP (всего: {xp['total_xp']})\n"
            f"📊 Сегодня: {fmt_minutes(today_min)} / {fmt_minutes(DAILY_BUDGET_MINUTES)}"
        )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶ Продолжить эту", callback_data="pomo_continue")],
            [InlineKeyboardButton("🔄 Другая задача", callback_data="pomo_switch")],
            [InlineKeyboardButton("☕ Перерыв 5мин", callback_data="pomo_break")],
            [InlineKeyboardButton("✅ Завершить задачу", callback_data=f"done_{active['task_id']}")],
        ])

        try:
            await context.bot.send_message(
                chat_id=OWNER_ID, text=text,
                parse_mode=ParseMode.HTML, reply_markup=kb,
            )
        except Exception as e:
            logger.error(f"Failed to send pomodoro notification: {e}")


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # ── Commands ──
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("focus", cmd_focus))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("rewards", cmd_rewards))
    app.add_handler(CommandHandler("goals", cmd_goals))
    app.add_handler(CommandHandler("debts", cmd_debts))
    app.add_handler(CommandHandler("sales", cmd_sales))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("schedule", cmd_schedule))

    # ── /add conversation ──
    add_conv = ConversationHandler(
        entry_points=[CommandHandler("add", cmd_add)],
        states={
            ADD_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_title_received)],
            ADD_GOAL: [CallbackQueryHandler(add_goal_selected, pattern=r"^addgoal_")],
        },
        fallbacks=[CommandHandler("cancel", add_cancel)],
        conversation_timeout=120,
    )
    app.add_handler(add_conv)

    # ── Inline callbacks ──
    app.add_handler(CallbackQueryHandler(callback_handler))

    # ── Reply keyboard text ──
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # ── Scheduled jobs ──
    jq = app.job_queue

    # Morning plan — 08:00 MSK
    jq.run_daily(
        morning_plan,
        time=dtime(hour=8, minute=0, tzinfo=MSK),
        name="morning_plan",
    )

    # Evening summary — 21:00 MSK
    jq.run_daily(
        evening_summary,
        time=dtime(hour=21, minute=0, tzinfo=MSK),
        name="evening_summary",
    )

    # Pomodoro checker — every 30 seconds
    jq.run_repeating(
        check_pomodoro,
        interval=30,
        first=10,
        name="check_pomodoro",
    )

    logger.info("Фокус-Трекер v2 запущен!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
