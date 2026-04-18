"""
Auto-task generation engine.
Создаёт задачи автоматически из шаблонов + стратегии.
"""
from datetime import date
import db

# ═══ TASK TEMPLATES: для каждой цели — паттерны задач ═══
# Формат: (goal_id, title, estimate_min)
# goal_id: 1=ниша, 2=revenue, 3=клиенты, 4=контент, 5=n8n, 6=курс

TEMPLATES = {
    1: [  # Ниша: тест 2-3 гипотез
        ("Изучить ТОП-10 конкурентов в нише {n}", 60),
        ("Составить SWOT-анализ ниши {n}", 45),
        ("Посчитать TAM/SAM/SOM для ниши {n}", 45),
        ("Провести 3 кастдев-интервью с ЦА ниши {n}", 90),
        ("Написать итоговый отчёт по нише {n}", 60),
    ],
    2: [  # Revenue модель
        ("Собрать бенчмарки CPL в нише", 60),
        ("Рассчитать LTV по модели pay-per-lead", 45),
        ("Построить юнит-экономику в Sheets", 90),
        ("Определить break-even point", 30),
        ("Сделать финмодель на 12 месяцев", 90),
        ("Протестировать ценовую гипотезу", 60),
    ],
    3: [  # Закрыть клиентов
        ("Написать холодный оффер v{n}", 60),
        ("Собрать базу 20 потенциальных клиентов", 60),
        ("Отписать 10 клиентов из базы", 45),
        ("Провести созвон с потенциальным клиентом", 45),
        ("Подготовить презентацию кейса", 60),
        ("Написать follow-up серию", 45),
        ("Закрыть клиента: провести финальный созвон", 60),
        ("Настроить рекламу для нового клиента", 90),
        ("Написать отчёт за первую неделю для клиента", 45),
    ],
    4: [  # Контентная воронка
        ("Написать пост для TG канала", 30),
        ("Написать скрипт для YouTube видео", 60),
        ("Записать YouTube видео", 120),
        ("Монтаж YouTube видео", 90),
        ("Сделать рилс / шортс из длинного видео", 30),
        ("Написать лид-магнит (PDF гайд)", 90),
        ("Настроить автоворонку в TG боте", 60),
    ],
    5: [  # n8n
        ("Настроить webhook для лидов", 60),
        ("Автоматизировать еженедельный отчёт клиенту", 90),
        ("Настроить нотификации о новых лидах в TG", 45),
        ("Автоматизировать сбор данных из CRM", 60),
        ("Создать дашборд для клиента в Sheets", 90),
    ],
    6: [  # Курс
        ("Написать план модуля {n}", 60),
        ("Записать лекцию модуля {n}", 120),
        ("Подготовить домашнее задание для модуля {n}", 45),
        ("Проверить и смонтировать модуль {n}", 60),
    ],
}


def get_existing_titles(goal_id):
    """Какие задачи уже есть у цели"""
    tasks = db.get_tasks_by_goal(goal_id)
    return {t["title"] for t in tasks}


def count_todo(goal_id):
    """Сколько незавершённых задач у цели"""
    tasks = db.get_tasks_by_goal(goal_id)
    return sum(1 for t in tasks if t["status"] in ("todo", "in_progress"))


def replenish_goal(goal_id, min_todo=2):
    """Добавляет задачи из шаблонов если todo < min_todo"""
    templates = TEMPLATES.get(goal_id, [])
    if not templates:
        return 0

    existing = get_existing_titles(goal_id)
    todo_count = count_todo(goal_id)
    added = 0

    if todo_count >= min_todo:
        return 0

    # Определяем номер (для шаблонов с {n})
    done_count = sum(1 for t in db.get_tasks_by_goal(goal_id) if t["status"] == "done")
    n = done_count + todo_count + 1

    for title_tpl, estimate in templates:
        if todo_count >= min_todo:
            break
        title = title_tpl.format(n=n)
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
    goals = db.get_goals(goal_type="work")
    total = 0
    for g in goals:
        added = replenish_goal(g["id"], min_todo)
        total += added
    return total


def generate_daily_plan(budget_min=240):
    """
    Генерирует оптимальный план дня:
    1. Пополняет бэклог если мало задач
    2. Подбирает задачи по приоритету
    3. Балансирует между целями (мин 2 цели)
    """
    # Шаг 1: пополняем
    replenish_all(min_todo=3)

    # Шаг 2: собираем все todo
    all_todo = db.get_tasks_for_date(None)

    # Шаг 3: приоритизация (ближе к деньгам = выше)
    priority_order = [3, 2, 1, 4, 5, 6]

    def prio(t):
        gid = t.get("goal_id") or 999
        try:
            return priority_order.index(gid)
        except ValueError:
            return 999

    candidates = sorted(all_todo, key=lambda t: (prio(t), t["estimate_min"]))

    # Шаг 4: набираем бюджет, стараясь покрыть мин 2 цели
    selected = []
    total = 0
    goals_covered = set()

    for t in candidates:
        if total + t["estimate_min"] > budget_min + 15:
            continue
        selected.append(t)
        total += t["estimate_min"]
        goals_covered.add(t.get("goal_id"))
        if total >= budget_min - 15 and len(goals_covered) >= 2:
            break

    # Шаг 5: планируем на сегодня
    today = date.today().isoformat()
    for t in selected:
        db.schedule_task(t["id"], today)

    return selected, total
