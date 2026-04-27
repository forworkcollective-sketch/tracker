"""
ФОКУС-ТРЕКЕР v2 — Seed данных
Загружает: долги, продукты, награды, расписание недели
Запусти один раз: python seed_focus.py
"""
import db

# ═══ 1. ОЧИСТКА (опционально — раскомментируй при первом запуске) ═══
# db.get_sb().table("tasks").delete().neq("id", 0).execute()
# db.get_sb().table("goals").delete().neq("id", 0).execute()
# db.get_sb().table("rewards").delete().neq("id", 0).execute()
# db.get_sb().table("schedule").delete().neq("id", 0).execute()

print("═══ ФОКУС-ТРЕКЕР v2 — Seed ═══\n")

# ═══ 2. ДОЛГИ (по приоритету погашения) ═══
debts = [
    {"title": "ФССП", "emoji": "🔓", "target_rub": 87000, "sort_order": 1,
     "description": "Разблокировка карт — КРИТИЧНО"},
    {"title": "Серёга", "emoji": "👤", "target_rub": 35000, "sort_order": 2,
     "description": "Долг человеку"},
    {"title": "Москвич-клиент", "emoji": "👤", "target_rub": 38000, "sort_order": 3,
     "description": "Долг клиенту"},
    {"title": "Сбербанк", "emoji": "🏦", "target_rub": 190000, "sort_order": 4,
     "description": "Просрочки"},
]

print("💰 Долги:")
for d in debts:
    gid = db.get_sb().table("goals").insert({
        "title": d["title"],
        "description": d.get("description", ""),
        "type": "debt",
        "zone": "debts",
        "target_rub": d["target_rub"],
        "paid_rub": 0,
        "emoji": d["emoji"],
        "status": "active",
        "priority": d["sort_order"],
        "color": "#dc2626",
    }).execute().data[0]["id"]
    print(f"  {d['emoji']} {d['title']} — {d['target_rub']//1000}к (id={gid})")

# ═══ 3. ПОДУШКА БЕЗОПАСНОСТИ ═══
gid = db.get_sb().table("goals").insert({
    "title": "Подушка безопасности",
    "description": "500к на чёрный день",
    "type": "savings",
    "zone": "future",
    "target_rub": 500000,
    "paid_rub": 0,
    "emoji": "🛡️",
    "status": "active",
    "priority": 5,
    "color": "#16a34a",
}).execute().data[0]["id"]
print(f"\n🛡️ Подушка безопасности — 500к (id={gid})")

# ═══ 4. РАБОЧИЕ ЦЕЛИ (каналы дохода) ═══
work_goals = [
    {"title": "Агентство", "emoji": "🏢", "color": "#6366f1",
     "description": "Клиенты, таргет, вайб-кодинг, боты"},
    {"title": "ПМ + маркетинг + СММ", "emoji": "📊", "color": "#8b5cf6",
     "description": "Кэштаун — проджект-менеджмент, СММ, маркетинг"},
    {"title": "Сайты / боты / трафик", "emoji": "🌐", "color": "#06b6d4",
     "description": "Отдельные каналы трафика, разработка"},
]

print("\n🎯 Рабочие цели:")
work_ids = []
for i, g in enumerate(work_goals):
    gid = db.get_sb().table("goals").insert({
        "title": g["title"],
        "description": g["description"],
        "type": "work",
        "zone": "work",
        "emoji": g["emoji"],
        "status": "active",
        "priority": i + 1,
        "color": g["color"],
    }).execute().data[0]["id"]
    work_ids.append(gid)
    print(f"  {g['emoji']} {g['title']} (id={gid})")

# ═══ 5. НАЧАЛЬНЫЕ ЗАДАЧИ ═══
initial_tasks = [
    # Агентство
    (work_ids[0], "Досмотреть уроки кэштауна", 60),
    (work_ids[0], "Выбрать нишу", 90),
    (work_ids[0], "Составить оффер для ниши", 60),
    (work_ids[0], "Собрать базу 50 потенциальных клиентов", 90),
    (work_ids[0], "Написать и отправить 10 КП", 60),
    (work_ids[0], "Провести первый созвон-диагностику", 45),
    (work_ids[0], "Закрыть первого клиента", 60),
    # ПМ + СММ
    (work_ids[1], "Описать пакет СММ-базовый (тексты)", 45),
    (work_ids[1], "Настроить Claude + VPS для генерации контента", 60),
    (work_ids[1], "Подготовить кейс/портфолио для СММ", 90),
    # Сайты/боты
    (work_ids[2], "Собрать шаблон сайта для быстрого запуска", 90),
    (work_ids[2], "Настроить пайплайн: заказ → бот → деплой", 60),
]

print("\n📋 Начальные задачи:")
for goal_id, title, est in initial_tasks:
    tid = db.add_task(goal_id, title, estimate_min=est)
    print(f"  ▸ {title} [{est}мин] (id={tid})")

# ═══ 6. НАГРАДЫ ═══
rewards = [
    ("🧋", "Вкусняшка", 30, "food"),
    ("☕", "Кофейня с Леной", 50, "food"),
    ("🎮", "Час игр", 50, "fun"),
    ("🍕", "Пицца из ресторана", 100, "food"),
    ("💸", "Донат блогеру", 100, "donate"),
    ("🍣", "Суши-сет", 150, "food"),
    ("🎯", "Кальянная", 150, "fun"),
    ("🛒", "Мелкая покупка до 2к", 200, "purchase"),
]

print("\n🎁 Награды:")
for emoji, title, cost, cat in rewards:
    db.get_sb().table("rewards").insert({
        "emoji": emoji, "title": title, "cost_xp": cost, "category": cat,
    }).execute()
    print(f"  {emoji} {title} — {cost} XP")

# ═══ 7. РАСПИСАНИЕ НЕДЕЛИ ═══
schedule = [
    (0, "Агентство + планёрка"),
    (1, "Контент свой + Агентство"),
    (2, "Агентство (продажи)"),
    (3, "Агентство (клиенты)"),
    (4, "Агентство + планёрка"),
    (5, "Сайты/боты (доп.проекты)"),
    (6, "Планирование недели"),
]

print("\n📅 Расписание недели:")
days_ru = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
for weekday, focus in schedule:
    hours = 0 if weekday == 6 else 4
    db.get_sb().table("schedule").insert({
        "weekday": weekday, "focus": focus, "hours": hours,
    }).execute()
    print(f"  {days_ru[weekday]}: {focus} ({hours}ч)")

# ═══ 8. XP АККАУНТ ═══
existing = db.get_sb().table("xp_account").select("id").execute()
if not existing.data:
    db.get_sb().table("xp_account").insert({"total_xp": 0, "level": 1}).execute()
    print("\n⭐ XP аккаунт создан (0 XP, уровень 1)")

print("\n═══ ГОТОВО! ═══")
print(f"Долгов: {len(debts)} ({sum(d['target_rub'] for d in debts)//1000}к)")
print(f"Рабочих целей: {len(work_goals)}")
print(f"Задач: {len(initial_tasks)}")
print(f"Наград: {len(rewards)}")
print(f"Цель: 850к (350к долги + 500к подушка)")
