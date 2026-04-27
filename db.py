"""
ФОКУС-ТРЕКЕР v2 — Supabase (PostgreSQL) database layer
"""
from datetime import datetime, date, timedelta, timezone
from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

def _now():
    return datetime.now(timezone.utc)

def _parse_dt(s):
    """Parse ISO datetime string ensuring timezone-aware result"""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

_client = None

def get_sb():
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ═══════════════════════════════════════════
# GOALS
# ═══════════════════════════════════════════

def add_goal(title, description="", target_hours=0, color="#6366f1", deadline=None, **kwargs):
    data = {
        "title": title,
        "description": description,
        "target_hours": target_hours,
        "color": color,
        "deadline": deadline,
        **kwargs,
    }
    res = get_sb().table("goals").insert(data).execute()
    return res.data[0]["id"]

def get_goals(status="active", goal_type=None):
    q = get_sb().table("goals").select("*").eq("status", status)
    if goal_type:
        q = q.eq("type", goal_type)
    res = q.order("priority").execute()
    return res.data

def get_debts():
    """Долги по приоритету"""
    return get_sb().table("goals").select("*").eq("type", "debt").eq("status", "active").order("priority").execute().data

def get_all_financial_goals():
    """Все финансовые цели: долги + подушка"""
    return get_sb().table("goals").select("*").in_("type", ["debt", "savings"]).eq("status", "active").order("priority").execute().data

def get_life_goals():
    """Все нерабочие цели, сгруппированные по зонам"""
    res = get_sb().table("goals").select("*").neq("type", "work").eq("status", "active").order("priority").execute()
    zones = {}
    for g in res.data:
        z = g.get("zone") or "other"
        zones.setdefault(z, []).append(g)
    return zones

def add_payment(goal_id, amount, note=""):
    """Внести платёж по финансовой цели"""
    sb = get_sb()
    sb.table("payments").insert({"goal_id": goal_id, "amount": amount, "note": note}).execute()
    goal = sb.table("goals").select("paid_rub, target_rub").eq("id", goal_id).limit(1).execute().data[0]
    new_paid = (goal.get("paid_rub") or 0) + amount
    updates = {"paid_rub": new_paid}
    if new_paid >= (goal.get("target_rub") or 0) and goal.get("target_rub"):
        updates["status"] = "completed"
    sb.table("goals").update(updates).eq("id", goal_id).execute()
    return new_paid

def get_goal(goal_id):
    res = get_sb().table("goals").select("*").eq("id", goal_id).limit(1).execute()
    return res.data[0] if res.data else None

def update_goal(goal_id, **kwargs):
    get_sb().table("goals").update(kwargs).eq("id", goal_id).execute()

def create_goal(**kwargs):
    res = get_sb().table("goals").insert(kwargs).execute()
    return res.data[0]["id"]

def delete_goal(goal_id):
    get_sb().table("goals").update({"status": "archived"}).eq("id", goal_id).execute()


# ═══════════════════════════════════════════
# TASKS
# ═══════════════════════════════════════════

def add_task(goal_id, title, estimate_min=60, priority=1, scheduled_date=None):
    data = {
        "goal_id": goal_id,
        "title": title,
        "estimate_min": estimate_min,
        "priority": priority,
        "scheduled_date": scheduled_date,
    }
    res = get_sb().table("tasks").insert(data).execute()
    return res.data[0]["id"]

def get_tasks_for_date(dt=None):
    sb = get_sb()
    query = sb.table("tasks").select("*, goals(title, color, emoji)")
    if dt:
        date_str = dt if isinstance(dt, str) else dt.isoformat()
        query = query.eq("scheduled_date", date_str).neq("status", "cancelled")
    else:
        query = query.eq("status", "todo")
    res = query.order("priority").execute()
    tasks = []
    for t in res.data:
        goal = t.pop("goals", None) or {}
        t["goal_title"] = goal.get("title")
        t["goal_color"] = goal.get("color")
        t["goal_emoji"] = goal.get("emoji", "🎯")
        tasks.append(t)
    return tasks

def get_task(task_id):
    res = get_sb().table("tasks").select("*, goals(title, color, emoji)").eq("id", task_id).limit(1).execute()
    if not res.data:
        return None
    t = res.data[0]
    goal = t.pop("goals", None) or {}
    t["goal_title"] = goal.get("title")
    t["goal_color"] = goal.get("color")
    t["goal_emoji"] = goal.get("emoji", "🎯")
    return t

def complete_task(task_id):
    get_sb().table("tasks").update({
        "status": "done",
        "completed_at": _now().isoformat()
    }).eq("id", task_id).execute()

def update_task(task_id, **kwargs):
    get_sb().table("tasks").update(kwargs).eq("id", task_id).execute()

def get_tasks_by_goal(goal_id):
    res = get_sb().table("tasks").select("*").eq("goal_id", goal_id).order("status").order("priority").execute()
    return res.data

def delete_task(task_id):
    get_sb().table("tasks").update({"status": "cancelled"}).eq("id", task_id).execute()

def schedule_task(task_id, dt):
    date_str = dt if isinstance(dt, str) else dt.isoformat()
    get_sb().table("tasks").update({"scheduled_date": date_str}).eq("id", task_id).execute()


# ═══════════════════════════════════════════
# TIME LOGS (Pomodoro)
# ═══════════════════════════════════════════

def start_timer(task_id):
    sb = get_sb()
    stop_active_timer()
    sb.table("tasks").update({"status": "in_progress"}).eq("id", task_id).execute()
    res = sb.table("time_logs").insert({
        "task_id": task_id,
        "started_at": _now().isoformat()
    }).execute()
    return res.data[0]["id"]

def stop_active_timer():
    sb = get_sb()
    res = sb.table("time_logs").select("*").is_("ended_at", "null").order("id", desc=True).limit(1).execute()
    if not res.data:
        return 0
    active = res.data[0]
    now = _now()
    started = datetime.fromisoformat(active["started_at"])
    duration = round((now - started).total_seconds() / 60, 1)
    sb.table("time_logs").update({
        "ended_at": now.isoformat(),
        "duration_min": duration
    }).eq("id", active["id"]).execute()
    return duration

def get_active_timer():
    sb = get_sb()
    res = sb.table("time_logs").select(
        "*, tasks(id, title, goal_id, goals(title, emoji))"
    ).is_("ended_at", "null").order("id", desc=True).limit(1).execute()
    if not res.data:
        return None
    row = res.data[0]
    # Авто-стоп таймеров старше 12 часов или с другого дня
    started = _parse_dt(row["started_at"])
    elapsed_hours = (_now() - started).total_seconds() / 3600
    if elapsed_hours > 12:
        duration = round(min(elapsed_hours * 60, 240), 1)  # макс 4ч
        sb.table("time_logs").update({
            "ended_at": _now().isoformat(),
            "duration_min": duration,
        }).eq("id", row["id"]).execute()
        return None
    task = row.pop("tasks", None) or {}
    goal = task.pop("goals", None) or {}
    return {
        **row,
        "task_id": task.get("id"),
        "task_title": task.get("title"),
        "goal_id": task.get("goal_id"),
        "goal_title": goal.get("title"),
        "goal_emoji": goal.get("emoji", "🎯"),
    }

def get_today_minutes():
    sb = get_sb()
    today = date.today().isoformat()
    res = sb.table("time_logs").select("started_at, duration_min, ended_at").gte(
        "started_at", today + "T00:00:00"
    ).lte("started_at", today + "T23:59:59").execute()
    total = 0
    for row in res.data:
        if row["ended_at"]:
            total += row["duration_min"] or 0
        else:
            elapsed = (_now() - _parse_dt(row["started_at"])).total_seconds() / 60
            total += elapsed
    return round(total, 1)

def get_today_pomodoros():
    """Количество завершённых помодорок (30мин блоков) сегодня"""
    mins = max(0, get_today_minutes())
    return int(mins // 30)

def get_daily_stats(days=30):
    sb = get_sb()
    since = (date.today() - timedelta(days=days)).isoformat() + "T00:00:00"
    res = sb.table("time_logs").select("started_at, duration_min").gte(
        "started_at", since
    ).not_.is_("ended_at", "null").execute()
    by_day = {}
    for row in res.data:
        day = row["started_at"][:10]
        by_day.setdefault(day, {"total_min": 0})
        by_day[day]["total_min"] += row["duration_min"] or 0
    return [
        {"day": day, "total_min": round(v["total_min"], 1)}
        for day, v in sorted(by_day.items())
    ]

def get_time_by_goal(days=30):
    sb = get_sb()
    since = (date.today() - timedelta(days=days)).isoformat() + "T00:00:00"
    res = sb.table("time_logs").select(
        "duration_min, tasks(goal_id, goals(id, title, color, emoji))"
    ).gte("started_at", since).not_.is_("ended_at", "null").execute()
    by_goal = {}
    for row in res.data:
        task = row.get("tasks") or {}
        goal = task.get("goals") or {}
        gid = goal.get("id")
        if not gid:
            continue
        if gid not in by_goal:
            by_goal[gid] = {"id": gid, "title": goal["title"], "color": goal["color"],
                            "emoji": goal.get("emoji", "🎯"), "total_min": 0}
        by_goal[gid]["total_min"] += row["duration_min"] or 0
    return sorted(by_goal.values(), key=lambda x: x["total_min"], reverse=True)

def get_today_breakdown():
    sb = get_sb()
    today = date.today().isoformat()
    res = sb.table("time_logs").select(
        "id, started_at, ended_at, duration_min, "
        "tasks(id, title, goal_id, goals(id, title, color, emoji))"
    ).gte("started_at", today + "T00:00:00").lte(
        "started_at", today + "T23:59:59"
    ).order("started_at").execute()
    entries = []
    for row in res.data:
        task = row.pop("tasks") or {}
        goal = (task.pop("goals", None) or {}) if task else {}
        duration = row["duration_min"] or 0
        if not row["ended_at"]:
            duration = (_now() - _parse_dt(row["started_at"])).total_seconds() / 60
        entries.append({
            "log_id": row["id"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "duration_min": round(duration, 1),
            "task_title": task.get("title", "?"),
            "task_id": task.get("id"),
            "goal_title": goal.get("title", "—"),
            "goal_color": goal.get("color", "#818cf8"),
            "goal_emoji": goal.get("emoji", "🎯"),
            "goal_id": goal.get("id"),
            "active": row["ended_at"] is None,
        })
    return entries

def get_today_by_goal():
    entries = get_today_breakdown()
    by_goal = {}
    for e in entries:
        gid = e["goal_id"] or 0
        if gid not in by_goal:
            by_goal[gid] = {
                "goal_id": gid, "title": e["goal_title"], "color": e["goal_color"],
                "emoji": e["goal_emoji"], "total_min": 0, "tasks": {},
            }
        by_goal[gid]["total_min"] += e["duration_min"]
        tid = e["task_id"]
        if tid not in by_goal[gid]["tasks"]:
            by_goal[gid]["tasks"][tid] = {"title": e["task_title"], "min": 0}
        by_goal[gid]["tasks"][tid]["min"] += e["duration_min"]
    result = []
    for gid, data in by_goal.items():
        data["tasks"] = list(data["tasks"].values())
        data["total_min"] = round(data["total_min"], 1)
        result.append(data)
    return sorted(result, key=lambda x: x["total_min"], reverse=True)

def get_goal_progress(goal_id):
    sb = get_sb()
    all_tasks = sb.table("tasks").select("id, status").eq("goal_id", goal_id).neq("status", "cancelled").execute()
    total = len(all_tasks.data)
    done = sum(1 for t in all_tasks.data if t["status"] == "done")
    task_ids = [t["id"] for t in all_tasks.data]
    hours = 0
    if task_ids:
        logs = sb.table("time_logs").select("duration_min").in_("task_id", task_ids).not_.is_("ended_at", "null").execute()
        hours = sum(r["duration_min"] or 0 for r in logs.data) / 60
    return {"total_tasks": total, "done_tasks": done, "hours_spent": round(hours, 1)}

def get_streak():
    sb = get_sb()
    res = sb.table("time_logs").select("started_at, duration_min").not_.is_("ended_at", "null").order("started_at", desc=True).execute()
    by_day = {}
    for row in res.data:
        day = row["started_at"][:10]
        by_day[day] = by_day.get(day, 0) + (row["duration_min"] or 0)
    streak = 0
    check = date.today()
    while True:
        ds = check.isoformat()
        if by_day.get(ds, 0) >= 60:
            streak += 1
            check -= timedelta(days=1)
        elif check == date.today() and by_day.get(ds, 0) < 60:
            check -= timedelta(days=1)
        else:
            break
    return streak


# ═══════════════════════════════════════════
# XP SYSTEM
# ═══════════════════════════════════════════

def get_xp():
    """Текущий XP и уровень"""
    res = get_sb().table("xp_account").select("*").order("id").limit(1).execute()
    if not res.data:
        get_sb().table("xp_account").insert({"total_xp": 0, "level": 1}).execute()
        return {"total_xp": 0, "level": 1}
    return res.data[0]

def add_xp(amount, reason=""):
    """Начислить XP"""
    sb = get_sb()
    acc = get_xp()
    new_total = acc["total_xp"] + amount
    new_level = _calc_level(new_total)
    sb.table("xp_account").update({
        "total_xp": new_total,
        "level": new_level,
        "updated_at": _now().isoformat(),
    }).eq("id", acc["id"]).execute()
    return {"total_xp": new_total, "level": new_level, "added": amount}

def _calc_level(xp):
    """Рассчитать уровень по XP"""
    thresholds = [0, 200, 500, 1000, 1500, 2500, 4000, 5500, 7500, 10000]
    level = 1
    for i, t in enumerate(thresholds):
        if xp >= t:
            level = i + 1
    return level

XP_POMODORO = 25
XP_TASK_DONE = 25
XP_FULL_DAY = 50
XP_ALL_TASKS = 30
XP_STREAK_MULTIPLIER = 10


# ═══════════════════════════════════════════
# REWARDS
# ═══════════════════════════════════════════

def get_rewards():
    """Каталог активных наград"""
    return get_sb().table("rewards").select("*").eq("active", True).order("cost_xp").execute().data

def get_reward(reward_id):
    res = get_sb().table("rewards").select("*").eq("id", reward_id).limit(1).execute()
    return res.data[0] if res.data else None

def claim_reward(reward_id):
    """Забрать награду за XP. Возвращает (success, message)"""
    reward = get_reward(reward_id)
    if not reward:
        return False, "Награда не найдена"
    xp = get_xp()
    if xp["total_xp"] < reward["cost_xp"]:
        return False, f"Не хватает XP: {xp['total_xp']}/{reward['cost_xp']}"
    sb = get_sb()
    # Списываем XP
    new_total = xp["total_xp"] - reward["cost_xp"]
    sb.table("xp_account").update({
        "total_xp": new_total,
        "level": _calc_level(new_total),
        "updated_at": _now().isoformat(),
    }).eq("id", xp["id"]).execute()
    # Записываем в историю
    sb.table("reward_claims").insert({
        "reward_id": reward_id,
        "reward_title": f"{reward['emoji']} {reward['title']}",
        "cost_xp": reward["cost_xp"],
    }).execute()
    return True, f"{reward['emoji']} {reward['title']} — забрано! (-{reward['cost_xp']} XP)"

def get_reward_history(limit=20):
    return get_sb().table("reward_claims").select("*").order("claimed_at", desc=True).limit(limit).execute().data

def create_reward(title, emoji="🎁", cost_xp=100, category="food"):
    res = get_sb().table("rewards").insert({
        "title": title, "emoji": emoji, "cost_xp": cost_xp, "category": category,
    }).execute()
    return res.data[0]["id"]

def update_reward(reward_id, **kwargs):
    get_sb().table("rewards").update(kwargs).eq("id", reward_id).execute()

def delete_reward(reward_id):
    get_sb().table("rewards").update({"active": False}).eq("id", reward_id).execute()


# ═══════════════════════════════════════════
# SALES
# ═══════════════════════════════════════════

def add_sale(product_type, revenue, cost, client_name="", note=""):
    """Внести продажу"""
    margin = revenue - cost
    res = get_sb().table("sales").insert({
        "product_type": product_type,
        "client_name": client_name,
        "revenue": revenue,
        "cost": cost,
        "margin": margin,
        "note": note,
    }).execute()
    return res.data[0]

def get_sales(days=30):
    since = (date.today() - timedelta(days=days)).isoformat() + "T00:00:00"
    return get_sb().table("sales").select("*").gte("sold_at", since).order("sold_at", desc=True).execute().data

def get_sales_summary(days=30):
    """Сводка продаж за период"""
    sales = get_sales(days)
    by_product = {}
    total_revenue = 0
    total_cost = 0
    total_margin = 0
    for s in sales:
        pt = s["product_type"]
        if pt not in by_product:
            by_product[pt] = {"count": 0, "revenue": 0, "cost": 0, "margin": 0}
        by_product[pt]["count"] += 1
        by_product[pt]["revenue"] += s["revenue"]
        by_product[pt]["cost"] += s["cost"]
        by_product[pt]["margin"] += s["margin"]
        total_revenue += s["revenue"]
        total_cost += s["cost"]
        total_margin += s["margin"]
    return {
        "total_clients": len(sales),
        "total_revenue": total_revenue,
        "total_cost": total_cost,
        "total_margin": total_margin,
        "by_product": by_product,
        "sales": sales,
    }

PRODUCT_NAMES = {
    "smm": "СММ-базовый",
    "dmp": "ДМП + оператор",
    "site_bot": "Сайт/бот/трафик",
}


# ═══════════════════════════════════════════
# SCHEDULE
# ═══════════════════════════════════════════

DAYS_RU = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]

def get_schedule():
    """Расписание недели"""
    return get_sb().table("schedule").select("*").order("weekday").execute().data

def get_today_schedule():
    """Фокус сегодня"""
    weekday = date.today().weekday()  # 0=ПН
    res = get_sb().table("schedule").select("*").eq("weekday", weekday).limit(1).execute()
    if res.data:
        return res.data[0]
    return {"weekday": weekday, "focus": "Свободный день", "hours": 4}

def update_schedule(weekday, focus, hours=4):
    sb = get_sb()
    existing = sb.table("schedule").select("id").eq("weekday", weekday).execute()
    if existing.data:
        sb.table("schedule").update({"focus": focus, "hours": hours}).eq("weekday", weekday).execute()
    else:
        sb.table("schedule").insert({"weekday": weekday, "focus": focus, "hours": hours}).execute()


# ═══════════════════════════════════════════
# DAILY SUMMARIES
# ═══════════════════════════════════════════

def save_daily_summary():
    """Сохранить итог дня"""
    today = date.today().isoformat()
    tasks = get_tasks_for_date(today)
    done = sum(1 for t in tasks if t["status"] == "done")
    total = len(tasks)
    focus_min = round(get_today_minutes())
    streak = get_streak()
    xp = get_xp()

    sb = get_sb()
    existing = sb.table("daily_summaries").select("id").eq("date", today).execute()
    data = {
        "date": today,
        "focus_minutes": focus_min,
        "tasks_done": done,
        "tasks_total": total,
        "xp_earned": 0,
        "streak": streak,
    }
    if existing.data:
        sb.table("daily_summaries").update(data).eq("date", today).execute()
    else:
        sb.table("daily_summaries").insert(data).execute()
    return data

def get_summaries(days=30):
    since = (date.today() - timedelta(days=days)).isoformat()
    return get_sb().table("daily_summaries").select("*").gte("date", since).order("date").execute().data


# ═══════════════════════════════════════════
# MILESTONES (Strategy Gantt) — JSON file storage
# ═══════════════════════════════════════════

import json as _json
import os as _os

_MILESTONES_FILE = _os.path.join(_os.path.dirname(__file__), "milestones.json")

def _load_milestones():
    try:
        with open(_MILESTONES_FILE, "r", encoding="utf-8") as f:
            return _json.load(f)
    except (FileNotFoundError, _json.JSONDecodeError):
        return []

def _save_milestones(data):
    with open(_MILESTONES_FILE, "w", encoding="utf-8") as f:
        _json.dump(data, f, ensure_ascii=False, indent=2)

def get_milestones():
    return sorted(_load_milestones(), key=lambda m: m.get("start_date", ""))

def create_milestone(phase, title, start_date, end_date, color="#8B0020", **kwargs):
    data = _load_milestones()
    new_id = max((m["id"] for m in data), default=0) + 1
    m = {"id": new_id, "phase": phase, "title": title,
         "start_date": start_date, "end_date": end_date,
         "color": color, "status": "todo", "priority": new_id, **kwargs}
    data.append(m)
    _save_milestones(data)
    return new_id

def update_milestone(mid, **kwargs):
    data = _load_milestones()
    for m in data:
        if m["id"] == mid:
            m.update(kwargs)
            break
    _save_milestones(data)

def delete_milestone(mid):
    data = [m for m in _load_milestones() if m["id"] != mid]
    _save_milestones(data)


# ═══════════════════════════════════════════
# CALENDAR QUERIES
# ═══════════════════════════════════════════

def get_tasks_for_range(start_date, end_date):
    """Tasks scheduled between two dates"""
    res = get_sb().table("tasks").select(
        "*, goals(title, color, emoji)"
    ).gte("scheduled_date", start_date).lte(
        "scheduled_date", end_date
    ).neq("status", "cancelled").order("priority").execute()
    tasks = []
    for t in res.data:
        goal = t.pop("goals", None) or {}
        t["goal_title"] = goal.get("title")
        t["goal_color"] = goal.get("color")
        t["goal_emoji"] = goal.get("emoji", "")
        tasks.append(t)
    return tasks

def get_timelogs_for_range(start_date, end_date):
    """Time logs for date range (for timeline view)"""
    res = get_sb().table("time_logs").select(
        "id, started_at, ended_at, duration_min, "
        "tasks(id, title, goal_id, goals(title, color, emoji))"
    ).gte("started_at", start_date + "T00:00:00").lte(
        "started_at", end_date + "T23:59:59"
    ).order("started_at").execute()
    entries = []
    for row in res.data:
        task = row.pop("tasks", None) or {}
        goal = task.pop("goals", None) or {}
        entries.append({
            "log_id": row["id"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "duration_min": row.get("duration_min") or 0,
            "task_id": task.get("id"),
            "task_title": task.get("title", "?"),
            "goal_color": goal.get("color", "#818cf8"),
            "goal_emoji": goal.get("emoji", ""),
        })
    return entries
