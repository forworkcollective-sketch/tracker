"""
Trigger Tracker — Telegram Bot
Трекер продуктивности: 4 часа в день на цели
"""
import asyncio
import logging
import re
from datetime import date, datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, BotCommand,
    MenuButtonWebApp, WebAppInfo,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

from config import BOT_TOKEN, OWNER_ID, DAILY_BUDGET_MINUTES, WEB_PORT
import db
import motivation
import autotasks

WEBAPP_URL = f"http://localhost:{WEB_PORT}"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ===== HELPERS =====

def fmt_minutes(mins):
    """Форматирует минуты в 'Xч Yмин'"""
    h = int(mins // 60)
    m = int(mins % 60)
    if h and m:
        return f"{h}ч {m}мин"
    elif h:
        return f"{h}ч"
    return f"{m}мин"

def progress_bar(current, total, length=10):
    """Визуальный прогресс-бар"""
    if total <= 0:
        return "░" * length
    filled = int(min(current / total, 1.0) * length)
    return "▓" * filled + "░" * (length - filled)

def is_owner(update: Update) -> bool:
    return update.effective_user.id == OWNER_ID


# ===== GOAL MATCHING =====

# Карта ключевых слов → паттерны для автоматического определения цели
# Расширяемый словарь: слова из текста пользователя → слова из названий целей
KEYWORD_SYNONYMS = {
    "пост": ["контент", "контентн", "smm", "соцсет", "блог", "канал", "telegram", "тг", "инстаграм", "instagram"],
    "контент": ["контент", "контентн", "smm", "соцсет", "блог", "канал", "воронк"],
    "канал": ["контент", "канал", "telegram", "тг", "блог"],
    "тг": ["контент", "канал", "telegram", "тг"],
    "рилс": ["контент", "smm", "видео", "reels"],
    "видео": ["контент", "видео", "reels", "монтаж"],
    "оффер": ["оффер", "продаж", "клиент", "лид", "лидген", "воронк", "продукт"],
    "клиент": ["клиент", "продаж", "лид", "лидген", "crm"],
    "лид": ["лид", "лидген", "клиент", "продаж", "воронк"],
    "продаж": ["продаж", "клиент", "лид", "revenue"],
    "сайт": ["сайт", "лендинг", "landing", "web", "веб"],
    "лендинг": ["сайт", "лендинг", "landing", "web"],
    "дизайн": ["дизайн", "креатив", "баннер", "визуал"],
    "креатив": ["креатив", "дизайн", "баннер", "контент"],
    "бот": ["бот", "автоматизац", "n8n", "telegram"],
    "автоматизац": ["автоматизац", "бот", "n8n", "скрипт"],
    "реклам": ["реклам", "трафик", "таргет", "ads", "маркетинг"],
    "таргет": ["таргет", "реклам", "трафик", "ads"],
    "трафик": ["трафик", "реклам", "таргет", "ads"],
    "аналитик": ["аналитик", "данн", "отчет", "метрик", "dashboard"],
    "отчет": ["отчет", "аналитик", "данн", "report"],
    "стратег": ["стратег", "план", "roadmap"],
    "план": ["план", "стратег", "roadmap"],
    "долг": ["долг", "кредит", "платеж", "финанс"],
    "кредит": ["долг", "кредит", "платеж"],
    "финанс": ["финанс", "бюджет", "деньг", "долг"],
    "рассылк": ["рассылк", "email", "письм", "контент"],
    "письм": ["письм", "рассылк", "email", "контент"],
    "презентац": ["презентац", "pitch", "предложен", "оффер"],
    "код": ["код", "разработк", "программ", "dev"],
    "разработк": ["разработк", "код", "программ", "dev"],
}

def match_goal_by_text(text: str) -> dict | None:
    """
    Пытается найти подходящую цель по тексту пользователя.
    Использует нечёткое совпадение ключевых слов.
    Возвращает goal dict или None.
    """
    goals = db.get_goals(goal_type="work")
    if not goals:
        return None

    text_lower = text.lower()
    text_words = re.findall(r'[а-яёa-z0-9]+', text_lower)

    best_goal = None
    best_score = 0

    for goal in goals:
        goal_title_lower = goal['title'].lower()
        goal_words = re.findall(r'[а-яёa-z0-9]+', goal_title_lower)
        score = 0

        # Прямое совпадение слов текста с названием цели
        for word in text_words:
            if len(word) < 3:
                continue
            for gw in goal_words:
                # Стемминг-лайт: совпадение начала слова (мин 4 символа)
                min_len = min(len(word), len(gw), 4)
                if word[:min_len] == gw[:min_len]:
                    score += 3
                    break

        # Расширенное совпадение через синонимы
        for word in text_words:
            if len(word) < 3:
                continue
            # Ищем синонимы для слова из текста
            for syn_key, syn_values in KEYWORD_SYNONYMS.items():
                if word.startswith(syn_key[:3]) or syn_key.startswith(word[:3]):
                    # Нашли синоним-ключ, теперь проверяем значения vs цель
                    for sv in syn_values:
                        for gw in goal_words:
                            if gw.startswith(sv[:3]) or sv.startswith(gw[:3]):
                                score += 1
                                break

        if score > best_score:
            best_score = score
            best_goal = goal

    # Минимальный порог совпадения
    if best_score >= 2:
        return best_goal
    return None


# Слова для быстрой остановки таймера
STOP_WORDS = {"стоп", "stop", "готово", "done", "пауза", "pause", "хватит", "всё", "все", "финиш"}


MAIN_KB = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📋 План на 4ч"), KeyboardButton("▶️ Статус")],
        [KeyboardButton("✅ Завершить"), KeyboardButton("📊 Сегодня")],
        [KeyboardButton("🎯 Работа"), KeyboardButton("💼 Жизнь")],
        [KeyboardButton("🔥 Streak"), KeyboardButton("💡 Предложи план")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


# ===== COMMANDS =====

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return await update.message.reply_text("⛔ Этот бот — личный трекер.")

    await update.message.reply_text(
        "🎯 *Trigger Tracker*\n\n"
        "4 часа в день — на то, что ведёт к цели.\n\n"
        "Жми кнопки внизу или 📋 слева от поля ввода.\n\n"
        "💬 Или просто напиши чем занимаешься — я запущу таймер.\n"
        "Напиши «стоп» когда закончишь.",
        parse_mode="Markdown",
        reply_markup=MAIN_KB,
    )


async def handle_reply_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия по reply-клавиатуре"""
    if not is_owner(update):
        return
    text = update.message.text
    mapping = {
        "📋 План на 4ч":      cmd_plan,
        "▶️ Статус":           cmd_status,
        "✅ Завершить":        cmd_done,
        "📊 Сегодня":          cmd_today,
        "🎯 Работа":           cmd_goals,
        "💼 Жизнь":            cmd_life,
        "🔥 Streak":           cmd_streak,
        "💡 Предложи план":    cmd_suggest,
    }
    handler = mapping.get(text)
    if handler:
        await handler(update, context)
        return True  # Обработано как кнопка
    return False  # Не кнопка — пусть обрабатывает free_text

async def cmd_goals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    goals = db.get_goals(goal_type="work")
    if not goals:
        return await update.message.reply_text("Рабочих целей нет. /addgoal чтобы добавить.")

    lines = ["🎯 *Рабочие цели:*\n"]
    for g in goals:
        progress = db.get_goal_progress(g['id'])
        pct = int(progress['done_tasks'] / max(progress['total_tasks'], 1) * 100)
        bar = progress_bar(progress['done_tasks'], progress['total_tasks'], 8)
        lines.append(
            f"*{g['title']}*\n"
            f"  {bar} {pct}% · {progress['done_tasks']}/{progress['total_tasks']} задач · {progress['hours_spent']}ч"
        )
    lines.append("\n💼 /life — жизненные цели (долги, путешествия, будущее)")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_life(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Жизненные цели: долги, покупки, путешествия, будущее"""
    if not is_owner(update):
        return
    zones = db.get_life_goals()
    meta = {
        "debts":  ("🔥 ДОЛГИ",        "Свобода от кредитов"),
        "goals":  ("🎯 ЦЕЛИ",          "Здоровье, покупки"),
        "travel": ("✈️ ПУТЕШЕСТВИЯ",   "Копим на трипы"),
        "future": ("💰 БУДУЩЕЕ",       "Подушка, пассивный доход"),
        "wife":   ("💕 ЖЕНЕ",          "Ленка"),
    }

    lines = ["*Жизненные цели — зачем ты работаешь 4ч/день:*\n"]
    total_remain = 0
    for zone_key, (title, desc) in meta.items():
        items = zones.get(zone_key, [])
        if not items:
            continue
        total_target = sum(g.get("target_rub") or 0 for g in items)
        total_paid = sum(g.get("paid_rub") or 0 for g in items)
        total_mo = sum(g.get("monthly_rub") or 0 for g in items)
        remain = max(total_target - total_paid, 0)
        total_remain += remain
        pct = int(total_paid / total_target * 100) if total_target > 0 else 0

        lines.append(f"\n{title} · _{desc}_")
        if total_target > 0:
            bar = progress_bar(total_paid, total_target, 10)
            lines.append(f"  {bar} {pct}%")
            lines.append(f"  💵 {total_paid:,}₽ / {total_target:,}₽".replace(",", " "))
            lines.append(f"  Осталось: *{remain:,}₽*".replace(",", " "))
        if total_mo > 0:
            lines.append(f"  📆 Ежемес: {total_mo:,}₽".replace(",", " "))

    lines.append(f"\n━━━━━━━━━━━━━━━━━━━")
    lines.append(f"*Итого осталось: {total_remain:,}₽*".replace(",", " "))
    lines.append(f"\n💳 /pay <id> <сумма> — внести платёж")
    lines.append(f"📋 /zone <debts|goals|travel|future|wife> — детали зоны")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_zone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детали конкретной зоны"""
    if not is_owner(update):
        return
    if not context.args:
        return await update.message.reply_text(
            "Формат: `/zone debts|goals|travel|future|wife`", parse_mode="Markdown"
        )

    zone = context.args[0]
    zones = db.get_life_goals()
    items = zones.get(zone, [])
    if not items:
        return await update.message.reply_text(f"Зона '{zone}' пуста")

    titles = {"debts": "🔥 Долги", "goals": "🎯 Цели", "travel": "✈️ Путешествия",
              "future": "💰 Будущее", "wife": "💕 Жене"}
    lines = [f"*{titles.get(zone, zone)}:*\n"]
    for g in items:
        emoji = g.get("emoji", "")
        title = g.get("title")
        target = g.get("target_rub") or 0
        paid = g.get("paid_rub") or 0
        mo = g.get("monthly_rub") or 0

        if target > 0:
            pct = int(paid / target * 100) if target else 0
            bar = progress_bar(paid, target, 6)
            lines.append(
                f"`#{g['id']:>3d}` {emoji} *{title}*\n"
                f"       {bar} {pct}% · {paid:,}/{target:,}₽".replace(",", " ")
            )
        elif mo > 0:
            lines.append(f"`#{g['id']:>3d}` {emoji} *{title}* — {mo:,}₽/мес".replace(",", " "))

    lines.append(f"\n💳 /pay <id> <сумма>")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Внести платёж: /pay <goal_id> <amount>"""
    if not is_owner(update):
        return
    if len(context.args) < 2:
        return await update.message.reply_text(
            "Формат: `/pay <id_цели> <сумма>`\n"
            "Пример: `/pay 7 5000` — внести 5000₽ на Сбербанк",
            parse_mode="Markdown"
        )
    try:
        goal_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        return await update.message.reply_text("Цифрами: `/pay 7 5000`", parse_mode="Markdown")

    goal = db.get_goal(goal_id)
    if not goal:
        return await update.message.reply_text(f"Цель #{goal_id} не найдена")

    new_paid = db.add_payment(goal_id, amount)
    target = goal.get("target_rub") or 0
    remain = max(target - new_paid, 0)
    pct = int(new_paid / target * 100) if target else 0

    msg = (
        f"✅ *+{amount:,}₽ → {goal['emoji']} {goal['title']}*\n\n".replace(",", " ") +
        f"Внесено: {new_paid:,}₽ / {target:,}₽ ({pct}%)\n".replace(",", " ") +
        f"Осталось: *{remain:,}₽*".replace(",", " ")
    )
    if remain == 0 and target > 0:
        msg += "\n\n🎉 *Цель закрыта!* 🔥"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_addgoal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    if not context.args:
        return await update.message.reply_text(
            "Формат: `/addgoal Название цели`\n"
            "Пример: `/addgoal Закрыть 5 клиентов на pay-per-lead`",
            parse_mode="Markdown"
        )

    title = " ".join(context.args)
    gid = db.add_goal(title)
    await update.message.reply_text(
        f"✅ Цель создана: *{title}*\n"
        f"ID: {gid}\n\n"
        f"Добавь задачи: `/add {gid} Название задачи | 60`\n"
        f"(60 = оценка в минутах)",
        parse_mode="Markdown"
    )

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить задачу: /add <goal_id> Название | минуты"""
    if not is_owner(update):
        return
    if len(context.args) < 2:
        return await update.message.reply_text(
            "Формат: `/add <goal_id> Название задачи | 60`",
            parse_mode="Markdown"
        )

    try:
        goal_id = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("Первый аргумент — ID цели (число)")

    rest = " ".join(context.args[1:])
    if "|" in rest:
        title, est = rest.rsplit("|", 1)
        title = title.strip()
        estimate = int(est.strip())
    else:
        title = rest
        estimate = 60

    today = date.today().isoformat()
    tid = db.add_task(goal_id, title, estimate, scheduled_date=today)
    await update.message.reply_text(
        f"✅ Задача добавлена: *{title}*\n"
        f"⏱ Оценка: {fmt_minutes(estimate)} · Цель ID: {goal_id}",
        parse_mode="Markdown"
    )

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать план на сегодня"""
    if not is_owner(update):
        return

    today = date.today().isoformat()
    tasks = db.get_tasks_for_date(today)
    worked = db.get_today_minutes()
    remaining = max(0, DAILY_BUDGET_MINUTES - worked)
    active = db.get_active_timer()

    lines = [
        f"📋 *План на {date.today().strftime('%d.%m.%Y')}*\n",
        f"⏱ {progress_bar(worked, DAILY_BUDGET_MINUTES, 12)} {fmt_minutes(worked)}/{fmt_minutes(DAILY_BUDGET_MINUTES)}",
        f"Осталось: *{fmt_minutes(remaining)}*\n"
    ]

    if active:
        elapsed = (datetime.now() - datetime.fromisoformat(active['started_at'])).total_seconds() / 60
        lines.append(f"▶️ Сейчас: *{active['task_title']}* — {fmt_minutes(elapsed)}\n")

    if not tasks:
        lines.append("_Задач на сегодня нет. Добавь через /add или /schedule_")
    else:
        buttons = []
        for t in tasks:
            icon = "✅" if t['status'] == 'done' else "▶️" if t['status'] == 'in_progress' else "⬜"
            goal_tag = f"[{t['goal_title']}]" if t.get('goal_title') else ""
            lines.append(f"{icon} *{t['title']}* — {fmt_minutes(t['estimate_min'])} {goal_tag}")

            if t['status'] == 'todo':
                buttons.append([InlineKeyboardButton(
                    f"▶️ {t['title'][:30]}", callback_data=f"start_{t['id']}"
                )])
            elif t['status'] == 'in_progress':
                buttons.append([InlineKeyboardButton(
                    f"⏹ Завершить: {t['title'][:25]}", callback_data=f"stop_{t['id']}"
                )])

        markup = InlineKeyboardMarkup(buttons) if buttons else None
        return await update.message.reply_text(
            "\n".join(lines), parse_mode="Markdown", reply_markup=markup
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запланировать незапланированные задачи на сегодня: /schedule"""
    if not is_owner(update):
        return

    unscheduled = db.get_tasks_for_date(None)  # все todo без даты
    if not unscheduled:
        return await update.message.reply_text("Все задачи уже запланированы или выполнены.")

    buttons = []
    for t in unscheduled[:10]:
        goal_tag = f"[{t['goal_title']}] " if t.get('goal_title') else ""
        buttons.append([InlineKeyboardButton(
            f"📅 {goal_tag}{t['title'][:30]} ({fmt_minutes(t['estimate_min'])})",
            callback_data=f"sched_{t['id']}"
        )])

    await update.message.reply_text(
        "📅 *Выбери задачи на сегодня:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    active = db.get_active_timer()
    if not active:
        return await update.message.reply_text("⏸ Таймер не запущен. Открой /plan и выбери задачу.")

    elapsed = (datetime.now() - datetime.fromisoformat(active['started_at'])).total_seconds() / 60
    await update.message.reply_text(
        f"▶️ *{active['task_title']}*\n"
        f"🎯 {active.get('goal_title', '—')}\n"
        f"⏱ Идёт: *{fmt_minutes(elapsed)}*\n",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏹ Завершить", callback_data=f"stop_{active['task_id']}"),
            InlineKeyboardButton("⏸ Пауза", callback_data=f"pause_{active['task_id']}")
        ]])
    )

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    streak = db.get_streak()
    worked_today = db.get_today_minutes()
    daily = db.get_daily_stats(7)
    by_goal = db.get_time_by_goal(7)

    lines = [
        "📊 *Статистика*\n",
        f"🔥 Streak: *{streak} дней*",
        f"⏱ Сегодня: *{fmt_minutes(worked_today)}* / {fmt_minutes(DAILY_BUDGET_MINUTES)}\n",
    ]

    if daily:
        lines.append("*Последние 7 дней:*")
        for d in daily[-7:]:
            bar = progress_bar(d['total_min'], DAILY_BUDGET_MINUTES, 8)
            lines.append(f"  {d['day'][5:]} {bar} {fmt_minutes(d['total_min'])}")

    if by_goal:
        lines.append("\n*По целям (7 дн):*")
        for g in by_goal:
            lines.append(f"  • {g['title']}: {fmt_minutes(g['total_min'])}")

    lines.append(f"\n🌐 Подробнее: дашборд /web")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детальный отчёт: куда ушли 4 часа сегодня"""
    if not is_owner(update):
        return

    entries = db.get_today_breakdown()
    by_goal = db.get_today_by_goal()
    worked = db.get_today_minutes()
    remaining = max(0, DAILY_BUDGET_MINUTES - worked)

    lines = [
        f"📊 *Сегодня · {date.today().strftime('%d.%m.%Y')}*\n",
        f"⏱ {progress_bar(worked, DAILY_BUDGET_MINUTES, 14)} {fmt_minutes(worked)}",
        f"Бюджет: {fmt_minutes(DAILY_BUDGET_MINUTES)} · Осталось: *{fmt_minutes(remaining)}*",
    ]

    if not entries:
        lines.append("\n_Сегодня таймер ещё не запускался._\n/plan → выбери задачу")
        return await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    # Разбивка по целям
    lines.append("\n*📍 Куда ушли часы:*")
    for g in by_goal:
        pct = int(g["total_min"] / max(worked, 1) * 100)
        bar = progress_bar(g["total_min"], worked, 10)
        lines.append(f"\n{g['emoji']} *{g['title']}* — {fmt_minutes(g['total_min'])} ({pct}%)")
        lines.append(f"  {bar}")
        for t in g["tasks"]:
            lines.append(f"  • {t['title']} — {fmt_minutes(t['min'])}")

    # Timeline
    lines.append("\n*⏰ Timeline:*")
    for e in entries:
        start = datetime.fromisoformat(e["started_at"]).strftime("%H:%M")
        end = datetime.fromisoformat(e["ended_at"]).strftime("%H:%M") if e["ended_at"] else "сейчас"
        tag = " ▶️" if e["active"] else ""
        lines.append(
            f"  `{start}–{end}` {e['goal_emoji']} {e['task_title'][:25]} · {fmt_minutes(e['duration_min'])}{tag}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_suggest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Умный план: авто-генерация задач + подбор по приоритету"""
    if not is_owner(update):
        return

    today = date.today().isoformat()
    already = db.get_tasks_for_date(today)

    # Авто-генерация через engine
    selected, total = autotasks.generate_daily_plan(DAILY_BUDGET_MINUTES)
    tasks = db.get_tasks_for_date(today)
    new_tasks = [t for t in tasks if t["id"] not in {a["id"] for a in already}]

    if not tasks:
        return await update.message.reply_text(
            "🤔 Бэклог пуст. Добавь задачи: /add <goal_id> название | минуты"
        )

    total_est = sum(t["estimate_min"] for t in tasks if t["status"] != "done")
    lines = [
        "💡 *План на 4ч — подобран по приоритету:*\n",
        "_Клиенты → деньги → долги → свобода_\n",
    ]
    buttons = []
    for t in tasks:
        if t["status"] == "done": continue
        icon = "▶️" if t["status"] == "in_progress" else "⬜"
        new = " 🆕" if t["id"] in {nt["id"] for nt in new_tasks} else ""
        tag = f"[{t.get('goal_title', '')}]"
        lines.append(f"  {icon} *{t['title']}*{new} · {fmt_minutes(t['estimate_min'])} {tag}")
        if t["status"] == "todo":
            buttons.append([InlineKeyboardButton(
                f"▶️ {t['title'][:30]}", callback_data=f"start_{t['id']}"
            )])

    lines.append(f"\n⏱ Итого: *{fmt_minutes(total_est)}*")
    if new_tasks:
        lines.append(f"🆕 Авто-добавлено: {len(new_tasks)} задач")

    await update.message.reply_text(
        "\n".join(lines), parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons) if buttons else MAIN_KB,
    )


async def cmd_streak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    streak = db.get_streak()
    if streak == 0:
        msg = "🔥 Streak: 0 дней\nНачни прямо сейчас — /plan"
    elif streak < 7:
        msg = f"🔥 Streak: *{streak} дней*\nПродолжай! До недельного streak осталось {7-streak} дней"
    else:
        msg = f"🔥🔥🔥 Streak: *{streak} дней*\nМощно! Ты в потоке."
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Быстро завершить текущую задачу"""
    if not is_owner(update):
        return
    duration = db.stop_active_timer()
    if not duration:
        return await update.message.reply_text("Нет активного таймера.")

    worked = db.get_today_minutes()
    remaining = max(0, DAILY_BUDGET_MINUTES - worked)

    # Найти текущую задачу и завершить
    sb = db.get_sb()
    res = sb.table("tasks").select("id, title").eq("status", "in_progress").limit(1).execute()
    if res.data:
        task = res.data[0]
        db.complete_task(task['id'])
        task_title = task['title']
    else:
        task_title = "задача"

    quote = motivation.get_done_quote()
    msg = (
        f"✅ *{task_title}* — готово за {fmt_minutes(duration)}!\n\n"
        f"_{quote}_\n\n"
        f"⏱ {progress_bar(worked, DAILY_BUDGET_MINUTES, 12)} {fmt_minutes(worked)}/{fmt_minutes(DAILY_BUDGET_MINUTES)}\n"
        f"Осталось: *{fmt_minutes(remaining)}*"
    )

    # Пополняем бэклог если мало задач
    autotasks.replenish_all(min_todo=2)

    if remaining > 0:
        today = date.today().isoformat()
        next_tasks = [t for t in db.get_tasks_for_date(today) if t['status'] == 'todo' and t['estimate_min'] <= remaining]
        if next_tasks:
            t = next_tasks[0]
            msg += f"\n\n➡️ Следующая: *{t['title']}* ({fmt_minutes(t['estimate_min'])})"
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton(f"▶️ Начать", callback_data=f"start_{t['id']}"),
                InlineKeyboardButton("☕ Перерыв", callback_data="break")
            ]])
            return await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=markup)
        else:
            msg += "\n\n🎉 Все задачи на сегодня выполнены!"
    else:
        msg += "\n\n🎉 *4 часа отработаны! Отличный день!*"

    await update.message.reply_text(msg, parse_mode="Markdown")


# ===== FREE TEXT INPUT & QUICK STOP =====

async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработка свободного текста:
    - Стоп-слова → остановка таймера
    - Любой другой текст → создание задачи + запуск таймера
    - Ответ на пинг «Занят другим» → ожидание описания
    """
    if not is_owner(update):
        return
    text = update.message.text.strip()

    # Проверяем: это кнопка reply-клавиатуры?
    button_texts = {"📋 План на 4ч", "▶️ Статус", "✅ Завершить", "📊 Сегодня",
                    "🎯 Работа", "💼 Жизнь", "🔥 Streak", "💡 Предложи план"}
    if text in button_texts:
        return  # Уже обработано handle_reply_button

    text_lower = text.lower().strip()

    # === QUICK STOP ===
    if text_lower in STOP_WORDS:
        active = db.get_active_timer()
        if not active:
            return await update.message.reply_text(
                "⏸ Таймер не запущен. Нечего останавливать.\n"
                "Напиши чем займёшься — запущу трек.",
                reply_markup=MAIN_KB,
            )
        duration = db.stop_active_timer()
        task_title = active.get('task_title', 'задача')
        goal_title = active.get('goal_title', '')

        # Помечаем задачу завершённой если стоп-слово = "готово"/"done"
        if text_lower in {"готово", "done"}:
            if active.get('task_id'):
                db.complete_task(active['task_id'])

        worked = db.get_today_minutes()
        remaining = max(0, DAILY_BUDGET_MINUTES - worked)

        goal_str = f" · {goal_title}" if goal_title else ""
        status_icon = "✅" if text_lower in {"готово", "done"} else "⏸"
        status_word = "Готово" if text_lower in {"готово", "done"} else "Пауза"

        msg = (
            f"{status_icon} *{status_word}: {task_title}*{goal_str}\n"
            f"⏱ Отработано: *{fmt_minutes(duration)}*\n\n"
            f"{progress_bar(worked, DAILY_BUDGET_MINUTES, 12)} {fmt_minutes(worked)}/{fmt_minutes(DAILY_BUDGET_MINUTES)}\n"
            f"Осталось: *{fmt_minutes(remaining)}*"
        )

        if remaining > 0:
            msg += "\n\n💬 Напиши чем займёшься дальше — запущу трек."
        else:
            msg += "\n\n🎉 *4 часа отработаны! Отличный день!*"

        return await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=MAIN_KB)

    # === Ожидание описания после «Занят другим» ===
    if context.user_data.get("waiting_for_activity"):
        context.user_data["waiting_for_activity"] = False
        # Продолжаем — обрабатываем как свободный ввод ниже

    # === FREE TEXT → создание задачи + запуск таймера ===

    # Если уже есть активный таймер — предложить сначала остановить
    active = db.get_active_timer()
    if active:
        elapsed = (datetime.now() - datetime.fromisoformat(active['started_at'])).total_seconds() / 60
        return await update.message.reply_text(
            f"⏱ Сейчас уже идёт таймер:\n"
            f"▶️ *{active['task_title']}* — {fmt_minutes(elapsed)}\n\n"
            f"Напиши «стоп» чтобы остановить, потом опиши новую задачу.",
            parse_mode="Markdown",
            reply_markup=MAIN_KB,
        )

    # Ограничим длину названия задачи
    task_title = text[:100].strip()
    if len(task_title) < 2:
        return  # Слишком короткое — игнорируем

    # Пытаемся найти подходящую цель
    matched_goal = match_goal_by_text(task_title)

    if matched_goal:
        goal_id = matched_goal['id']
        goal_title = matched_goal['title']
    else:
        # Если целей нет вообще — берём первую рабочую или создаём без цели
        goals = db.get_goals(goal_type="work")
        if goals:
            # Берём первую (самый высокий приоритет)
            goal_id = goals[0]['id']
            goal_title = goals[0]['title']
        else:
            goal_id = None
            goal_title = "Без цели"

    # Создаём задачу на сегодня
    today = date.today().isoformat()
    if goal_id:
        tid = db.add_task(goal_id, task_title, estimate_min=60, scheduled_date=today)
    else:
        # Fallback: нужен goal_id, создадим общую цель
        gid = db.add_goal("Разное", description="Задачи без конкретной цели")
        tid = db.add_task(gid, task_title, estimate_min=60, scheduled_date=today)
        goal_title = "Разное"

    # Запускаем таймер
    db.start_timer(tid)

    await update.message.reply_text(
        f"⏱ *Запустил таймер:* {task_title} · _{goal_title}_\n\n"
        f"Напиши «стоп» когда закончишь.",
        parse_mode="Markdown",
        reply_markup=MAIN_KB,
    )


# ===== CALLBACKS =====

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("start_"):
        task_id = int(data.split("_")[1])
        task = db.get_task(task_id)
        if not task:
            return await query.edit_message_text("Задача не найдена.")

        db.start_timer(task_id)
        await query.edit_message_text(
            f"▶️ *Таймер запущен!*\n\n"
            f"📌 {task['title']}\n"
            f"🎯 {task.get('goal_title', '—')}\n"
            f"⏱ Оценка: {fmt_minutes(task['estimate_min'])}\n\n"
            f"Когда закончишь — напиши «стоп» или /done",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Готово", callback_data=f"stop_{task_id}"),
                InlineKeyboardButton("⏸ Пауза", callback_data=f"pause_{task_id}")
            ]])
        )

    elif data.startswith("stop_"):
        task_id = int(data.split("_")[1])
        duration = db.stop_active_timer()
        db.complete_task(task_id)
        task = db.get_task(task_id)

        worked = db.get_today_minutes()
        remaining = max(0, DAILY_BUDGET_MINUTES - worked)

        msg = (
            f"✅ *{task['title'] if task else 'Задача'}* — готово за {fmt_minutes(duration)}!\n\n"
            f"⏱ {fmt_minutes(worked)} / {fmt_minutes(DAILY_BUDGET_MINUTES)} · Осталось: {fmt_minutes(remaining)}"
        )

        if remaining > 0:
            today = date.today().isoformat()
            next_tasks = [t for t in db.get_tasks_for_date(today) if t['status'] == 'todo' and t['estimate_min'] <= remaining]
            if next_tasks:
                t = next_tasks[0]
                msg += f"\n\n➡️ Следующая: *{t['title']}* ({fmt_minutes(t['estimate_min'])})"
                markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton(f"▶️ Начать", callback_data=f"start_{t['id']}"),
                    InlineKeyboardButton("⏸ Перерыв", callback_data="break")
                ]])
                return await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=markup)

        msg += "\n\n💬 Напиши чем займёшься дальше — запущу трек."
        await query.edit_message_text(msg, parse_mode="Markdown")

    elif data.startswith("pause_"):
        duration = db.stop_active_timer()
        await query.edit_message_text(
            f"⏸ Пауза. Отработано: {fmt_minutes(duration)}\n"
            f"Продолжить — /plan или напиши чем займёшься",
            parse_mode="Markdown"
        )

    elif data.startswith("sched_all_"):
        ids = [int(x) for x in data.replace("sched_all_", "").split(",") if x]
        today = date.today().isoformat()
        for tid in ids:
            db.schedule_task(tid, today)
        await query.edit_message_text(
            f"✅ *{len(ids)} задач запланированы на сегодня*\n\nЖми 📋 План на 4ч → начать",
            parse_mode="Markdown"
        )

    elif data.startswith("sched_"):
        task_id = int(data.split("_")[1])
        today = date.today().isoformat()
        db.schedule_task(task_id, today)
        task = db.get_task(task_id)
        await query.edit_message_text(
            f"📅 *{task['title']}* запланирована на сегодня!",
            parse_mode="Markdown"
        )

    elif data == "break":
        await query.edit_message_text(
            "☕ Отдыхай! Когда будешь готов — напиши чем займёшься или /plan",
            parse_mode="Markdown"
        )

    elif data == "ping_ok":
        await query.edit_message_text("👍 Работай! Пискну через 30 мин если ещё идёт.")

    elif data == "ping_done":
        # Callback: «Нет, закончил» из пинга
        active = db.get_active_timer()
        if active:
            duration = db.stop_active_timer()
            if active.get('task_id'):
                db.complete_task(active['task_id'])
            worked = db.get_today_minutes()
            remaining = max(0, DAILY_BUDGET_MINUTES - worked)
            await query.edit_message_text(
                f"✅ *{active.get('task_title', 'Задача')}* — готово за {fmt_minutes(duration)}!\n\n"
                f"⏱ {fmt_minutes(worked)}/{fmt_minutes(DAILY_BUDGET_MINUTES)} · Осталось: {fmt_minutes(remaining)}\n\n"
                f"💬 Напиши чем займёшься дальше.",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text("Таймер уже остановлен.")

    elif data == "ping_other":
        # Callback: «Занят другим» из пинга — остановить текущий таймер и ждать описание
        active = db.get_active_timer()
        if active:
            duration = db.stop_active_timer()
            await query.edit_message_text(
                f"⏸ Остановил *{active.get('task_title', 'задачу')}* ({fmt_minutes(duration)})\n\n"
                f"💬 Чем занят? Напиши — и я запущу трек.",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                "💬 Чем занят? Напиши — и я запущу трек.",
                parse_mode="Markdown"
            )
        # Ставим флаг ожидания
        context.user_data["waiting_for_activity"] = True

    elif data == "show_plan":
        # Фейковый update.message для вызова cmd_plan
        await query.message.reply_text("Открываю план…")
        fake_update = Update(update.update_id, message=query.message)
        await cmd_plan(fake_update, context)

    elif data == "suggest":
        await query.message.reply_text("Подбираю план по приоритету…")
        fake_update = Update(update.update_id, message=query.message)
        await cmd_suggest(fake_update, context)


# ===== MORNING NOTIFICATION =====

async def send_morning_plan(context: ContextTypes.DEFAULT_TYPE):
    """9:00 — план дня с авто-задачами + мотивационное фото"""
    today = date.today().isoformat()
    tasks = db.get_tasks_for_date(today)

    if not tasks:
        # Авто-генерация через engine
        selected, total = autotasks.generate_daily_plan(DAILY_BUDGET_MINUTES)
        tasks = db.get_tasks_for_date(today)

    if not tasks:
        return await context.bot.send_photo(
            OWNER_ID,
            photo=motivation.get_image("morning"),
            caption="🌅 Доброе утро!\n\nЗадач нет — жми 💡 Предложи план\nИли просто напиши чем займёшься.",
            reply_markup=MAIN_KB,
        )

    total_est = sum(t['estimate_min'] for t in tasks if t['status'] != 'done')
    quote = motivation.get_morning_quote()
    lines = [
        f"🌅 *План на 4 часа*\n",
        f"_{quote}_\n",
        f"📋 {len(tasks)} задач · {fmt_minutes(total_est)}\n",
    ]
    buttons = []
    for t in tasks:
        if t['status'] == 'done': continue
        goal_tag = f"[{t['goal_title']}]" if t.get('goal_title') else ""
        lines.append(f"⬜ *{t['title']}* · {fmt_minutes(t['estimate_min'])} {goal_tag}")
        buttons.append([InlineKeyboardButton(
            f"▶️ {t['title'][:30]}", callback_data=f"start_{t['id']}"
        )])
    lines.append("\n💪 Погнали! Или просто напиши чем займёшься.")

    await context.bot.send_photo(
        OWNER_ID,
        photo=motivation.get_image("morning"),
        caption="\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons) if buttons else MAIN_KB,
    )


async def send_midday_check(context: ContextTypes.DEFAULT_TYPE):
    """12:00 — если не начал работать, спросить"""
    worked = db.get_today_minutes()
    active = db.get_active_timer()

    if active:
        # Уже работает — спросить всё ли ок
        elapsed = (datetime.now() - datetime.fromisoformat(active['started_at'])).total_seconds() / 60
        await context.bot.send_message(
            OWNER_ID,
            f"☀️ *Полдень!* Таймер идёт: *{active['task_title']}* — {fmt_minutes(elapsed)}\n\n"
            f"Сейчас работаешь? Над чем?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Да, продолжаю", callback_data="ping_ok")],
                [InlineKeyboardButton("⏹ Нет, закончил", callback_data="ping_done")],
                [InlineKeyboardButton("🔄 Занят другим", callback_data="ping_other")],
            ])
        )
        return

    if worked >= 30:
        return  # Уже поработал — не мешаем

    today = date.today().isoformat()
    tasks = db.get_tasks_for_date(today)
    todo = [t for t in tasks if t['status'] == 'todo']

    if not todo:
        await context.bot.send_message(
            OWNER_ID,
            "☀️ *Полдень!* Таймер ещё не щёлкал.\n\n"
            "Сейчас работаешь? Над чем?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Открыть план", callback_data="show_plan")],
                [InlineKeyboardButton("🔄 Занят другим", callback_data="ping_other")],
            ])
        )
        return

    t = todo[0]
    await context.bot.send_message(
        OWNER_ID,
        f"☀️ *Полдень!* Таймер ещё не щёлкал.\n\n"
        f"Сейчас работаешь? Над чем?\n\n"
        f"Предлагаю начать с *{t['title']}* ({fmt_minutes(t['estimate_min'])})",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"▶️ Начать: {t['title'][:25]}", callback_data=f"start_{t['id']}")],
            [InlineKeyboardButton("📋 Весь план", callback_data="show_plan")],
            [InlineKeyboardButton("🔄 Занят другим", callback_data="ping_other")],
        ])
    )


async def send_afternoon_pulse(context: ContextTypes.DEFAULT_TYPE):
    """15:00 — прогресс 4ч"""
    worked = db.get_today_minutes()
    active = db.get_active_timer()
    if active:
        return
    remaining = max(0, DAILY_BUDGET_MINUTES - worked)
    if remaining <= 15:
        return
    pct = int(worked / DAILY_BUDGET_MINUTES * 100)
    bar = progress_bar(worked, DAILY_BUDGET_MINUTES, 12)
    await context.bot.send_message(
        OWNER_ID,
        f"☕ *15:00 · Прогресс дня*\n\n"
        f"{bar} {pct}%\n"
        f"Поработал: {fmt_minutes(worked)} · Осталось: *{fmt_minutes(remaining)}*\n\n"
        f"Пора продолжать? Напиши чем займёшься или выбери из плана.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 План", callback_data="show_plan"),
             InlineKeyboardButton("💡 Предложи", callback_data="suggest")],
            [InlineKeyboardButton("🔄 Занят другим", callback_data="ping_other")],
        ])
    )


async def send_evening_summary(context: ContextTypes.DEFAULT_TYPE):
    """21:00 — итог дня с фото + разбивка по целям + авто-пополнение бэклога"""
    worked = db.get_today_minutes()
    by_goal = db.get_today_by_goal()
    streak = db.get_streak()

    # Пополняем бэклог на завтра
    added = autotasks.replenish_all(min_todo=3)

    good_day = worked >= DAILY_BUDGET_MINUTES * 0.5

    if worked < 10:
        quote = motivation.get_evening_quote(good=False)
        return await context.bot.send_photo(
            OWNER_ID,
            photo=motivation.get_image("evening"),
            caption=f"🌙 {quote}\n\nStreak: {streak}. Завтра — новый шанс.",
            reply_markup=MAIN_KB,
        )

    pct = int(worked / DAILY_BUDGET_MINUTES * 100)
    quote = motivation.get_evening_quote(good=good_day)

    lines = [
        f"🌙 *Итог дня · {date.today().strftime('%d.%m')}*\n",
        f"⏱ {progress_bar(worked, DAILY_BUDGET_MINUTES, 14)} {pct}%",
        f"Отработано: *{fmt_minutes(worked)}* · 🔥 {streak}\n",
        f"_{quote}_",
    ]
    if by_goal:
        lines.append("\n*📍 Куда ушли часы:*")
        for g in by_goal:
            lines.append(f"  {g['emoji']} {g['title']} — {fmt_minutes(g['total_min'])}")

    if added:
        lines.append(f"\n♻️ +{added} новых задач добавлено в бэклог на завтра")

    img = "day_complete" if worked >= DAILY_BUDGET_MINUTES else "evening"
    await context.bot.send_photo(
        OWNER_ID,
        photo=motivation.get_image(img),
        caption="\n".join(lines),
        parse_mode="Markdown",
        reply_markup=MAIN_KB,
    )


async def check_long_timer(context: ContextTypes.DEFAULT_TYPE):
    """Каждые 30 мин: если таймер идёт > 90 мин — спросить"""
    active = db.get_active_timer()
    if not active:
        return
    started = datetime.fromisoformat(active['started_at'])
    elapsed = (datetime.now() - started).total_seconds() / 60
    if elapsed < 90:
        return
    # Не пиналим слишком часто — проверяем флаг в bot_data
    last_ping = context.bot_data.get("last_long_ping")
    if last_ping and (datetime.now() - last_ping).total_seconds() < 1800:
        return
    context.bot_data["last_long_ping"] = datetime.now()

    await context.bot.send_message(
        OWNER_ID,
        f"⏰ Таймер *{active['task_title']}* идёт уже *{fmt_minutes(elapsed)}*.\n\n"
        f"Сейчас работаешь? Над чем?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да, продолжаю", callback_data="ping_ok")],
            [InlineKeyboardButton("⏹ Нет, закончил", callback_data="ping_done")],
            [InlineKeyboardButton("🔄 Занят другим", callback_data="ping_other")],
        ])
    )


# ===== MAIN =====

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("goals", cmd_goals))
    app.add_handler(CommandHandler("life", cmd_life))
    app.add_handler(CommandHandler("zone", cmd_zone))
    app.add_handler(CommandHandler("pay", cmd_pay))
    app.add_handler(CommandHandler("addgoal", cmd_addgoal))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("suggest", cmd_suggest))
    app.add_handler(CommandHandler("streak", cmd_streak))
    app.add_handler(CommandHandler("done", cmd_done))

    # Reply keyboard buttons (higher priority — group 0)
    app.add_handler(MessageHandler(
        filters.Regex(r'^(📋 План на 4ч|▶️ Статус|✅ Завершить|📊 Сегодня|🎯 Работа|💼 Жизнь|🔥 Streak|💡 Предложи план)$'),
        handle_reply_button
    ))

    # Free text handler (lower priority — group 1, registered LAST)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_free_text
    ), group=1)

    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Регистрируем команды в меню TG (слева от поля ввода)
    async def post_init(application: Application):
        commands = [
            BotCommand("plan",    "📋 План на 4ч"),
            BotCommand("suggest", "💡 Умный план по приоритету"),
            BotCommand("today",   "📊 Куда ушли часы сегодня"),
            BotCommand("status",  "▶️ Текущий таймер"),
            BotCommand("done",    "✅ Завершить задачу"),
            BotCommand("goals",   "🎯 Рабочие цели"),
            BotCommand("life",    "💼 Жизненные цели"),
            BotCommand("zone",    "📋 Детали зоны (debts/goals/travel/future)"),
            BotCommand("pay",     "💳 Внести платёж по цели"),
            BotCommand("stats",   "📈 Статистика"),
            BotCommand("streak",  "🔥 Серия дней"),
            BotCommand("add",     "➕ Добавить задачу"),
            BotCommand("addgoal", "➕ Добавить цель"),
            BotCommand("start",   "🏠 Главное меню"),
        ]
        await application.bot.set_my_commands(commands)
        # WebApp button слева от поля ввода (для локальной разработки — localhost)
        # Для продакшена заменить на https://domain
        try:
            await application.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="📊 Tracker",
                    web_app=WebAppInfo(url=WEBAPP_URL)
                )
            )
        except Exception:
            pass  # WebApp requires HTTPS in production

    app.post_init = post_init

    # Напоминания (по МСК)
    if OWNER_ID:
        from datetime import time as dtime
        import pytz
        tz = pytz.timezone("Europe/Moscow")
        jq = app.job_queue
        jq.run_daily(send_morning_plan,    time=dtime(9, 0,  tzinfo=tz))
        jq.run_daily(send_midday_check,    time=dtime(12, 0, tzinfo=tz))
        jq.run_daily(send_afternoon_pulse, time=dtime(15, 0, tzinfo=tz))
        jq.run_daily(send_evening_summary, time=dtime(21, 0, tzinfo=tz))
        jq.run_repeating(check_long_timer, interval=1800, first=1800)  # каждые 30 мин

    logger.info("Trigger Tracker bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
