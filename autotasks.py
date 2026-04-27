"""
ФОКУС-ТРЕКЕР v2 — Auto-task generation engine.
Создаёт задачи автоматически из шаблонов по каналам дохода.
"""
from datetime import date
import db

# ═══ TASK TEMPLATES: для каждого канала дохода ═══
# Ключ = goal_id (будет заменён при запуске на реальные ID)

TEMPLATES_BY_TITLE = {
    "Агентство": [
        ("Изучить урок кэштауна #{n}", 60),
        ("Составить оффер для ниши #{n}", 60),
        ("Собрать базу 20 потенциальных клиентов", 60),
        ("Отправить 10 КП в директ", 45),
        ("Написать follow-up 10 клиентам", 30),
        ("Провести созвон-диагностику с клиентом", 45),
        ("Подготовить презентацию/кейс", 60),
        ("Закрыть сделку: финальный созвон", 45),
        ("Настроить рекламу для клиента", 90),
        ("Написать отчёт клиенту за неделю", 45),
        ("Планёрка: ключевые метрики + допродажи", 30),
    ],
    "ПМ + маркетинг + СММ": [
        ("Описать пакет СММ-базовый (что входит)", 45),
        ("Настроить Claude + VPS для генерации контента", 60),
        ("Написать 5 постов для клиента", 60),
        ("Подготовить контент-план на месяц", 45),
        ("Создать визуал-шаблоны для соцсетей", 60),
        ("Написать стратегию продвижения для клиента", 90),
        ("Настроить автопостинг", 45),
        ("Подготовить кейс/портфолио для продажи СММ", 60),
    ],
    "Сайты / боты / трафик": [
        ("Собрать шаблон лендинга для быстрого запуска", 90),
        ("Настроить Яндекс Директ для клиента", 90),
        ("Создать ТГ-бот для клиента", 120),
        ("Настроить аналитику (Метрика/GTM)", 45),
        ("A/B тест рекламных креативов", 60),
        ("Написать тексты для лендинга", 60),
        ("Запустить тестовую рекламную кампанию", 60),
    ],
}


def _get_goal_id_by_title(title_prefix):
    """Найти goal_id по началу названия"""
    goals = db.get_goals(goal_type="work")
    for g in goals:
        if g["title"].startswith(title_prefix):
            return g["id"]
    return None


def get_existing_titles(goal_id):
    tasks = db.get_tasks_by_goal(goal_id)
    return {t["title"] for t in tasks}


def count_todo(goal_id):
    tasks = db.get_tasks_by_goal(goal_id)
    return sum(1 for t in tasks if t["status"] in ("todo", "in_progress"))


def replenish_goal(goal_id, templates, min_todo=2):
    """Добавляет задачи из шаблонов если todo < min_todo"""
    if not templates:
        return 0

    existing = get_existing_titles(goal_id)
    todo_count = count_todo(goal_id)
    added = 0

    if todo_count >= min_todo:
        return 0

    done_count = sum(1 for t in db.get_tasks_by_goal(goal_id) if t["status"] == "done")
    n = done_count + todo_count + 1

    for title_tpl, estimate in templates:
        if todo_count >= min_todo:
            break
        title = title_tpl.replace("{n}", str(n))
        if title in existing:
            n += 1
            continue
        db.add_task(goal_id, title, estimate_min=estimate)
        existing.add(title)
        todo_count += 1
        added += 1
        n += 1

    return added


def replenish_all(min_todo=2):
    """Пополнить все рабочие цели"""
    total = 0
    for title_prefix, templates in TEMPLATES_BY_TITLE.items():
        goal_id = _get_goal_id_by_title(title_prefix)
        if goal_id:
            added = replenish_goal(goal_id, templates, min_todo)
            total += added
    return total


def generate_daily_plan(budget_min=240):
    """
    Генерирует план дня:
    1. Пополняет бэклог если мало задач
    2. Учитывает день недели (расписание)
    3. Подбирает задачи по приоритету
    """
    replenish_all(min_todo=3)

    # Получаем фокус дня
    schedule = db.get_today_schedule()
    focus = schedule.get("focus", "").lower()

    all_todo = db.get_tasks_for_date(None)
    goals = db.get_goals(goal_type="work")
    goal_ids = [g["id"] for g in goals]

    # Приоритизация: цели по фокусу дня имеют приоритет
    focus_goal_ids = set()
    for g in goals:
        if any(word in g["title"].lower() for word in focus.split()):
            focus_goal_ids.add(g["id"])

    def prio(t):
        gid = t.get("goal_id") or 999
        # Задачи по фокусу дня — приоритет 0
        if gid in focus_goal_ids:
            return 0
        # Остальные рабочие — по порядку
        try:
            return goal_ids.index(gid) + 1
        except ValueError:
            return 999

    candidates = sorted(all_todo, key=lambda t: (prio(t), t["estimate_min"]))

    selected = []
    total = 0
    goals_covered = set()

    for t in candidates:
        if total + t["estimate_min"] > budget_min + 15:
            continue
        selected.append(t)
        total += t["estimate_min"]
        goals_covered.add(t.get("goal_id"))
        if total >= budget_min - 15 and len(goals_covered) >= 1:
            break

    today = date.today().isoformat()
    for t in selected:
        db.schedule_task(t["id"], today)

    return selected, total
