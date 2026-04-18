"""
Trigger Tracker — Supabase (PostgreSQL) database layer
"""
from datetime import datetime, date, timedelta
from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

_client = None

def get_sb():
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ===== GOALS =====

def add_goal(title, description="", target_hours=0, color="#6366f1", deadline=None):
    data = {
        "title": title,
        "description": description,
        "target_hours": target_hours,
        "color": color,
        "deadline": deadline,
    }
    res = get_sb().table("goals").insert(data).execute()
    return res.data[0]["id"]

def get_goals(status="active", goal_type=None):
    q = get_sb().table("goals").select("*").eq("status", status)
    if goal_type:
        q = q.eq("type", goal_type)
    res = q.order("priority").execute()
    return res.data

def get_life_goals():
    """Все нерабочие цели, сгруппированные по зонам"""
    res = get_sb().table("goals").select("*").neq("type", "work").eq("status", "active").order("id").execute()
    zones = {}
    for g in res.data:
        z = g.get("zone") or "other"
        zones.setdefault(z, []).append(g)
    return zones

def add_payment(goal_id, amount, note=""):
    """Внести платёж по финансовой цели"""
    sb = get_sb()
    sb.table("payments").insert({"goal_id": goal_id, "amount": amount, "note": note}).execute()
    # Увеличиваем paid_rub
    goal = sb.table("goals").select("paid_rub").eq("id", goal_id).limit(1).execute().data[0]
    new_paid = (goal.get("paid_rub") or 0) + amount
    sb.table("goals").update({"paid_rub": new_paid}).eq("id", goal_id).execute()
    return new_paid

def get_goal(goal_id):
    res = get_sb().table("goals").select("*").eq("id", goal_id).limit(1).execute()
    return res.data[0] if res.data else None

def update_goal(goal_id, **kwargs):
    get_sb().table("goals").update(kwargs).eq("id", goal_id).execute()


# ===== TASKS =====

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
    query = sb.table("tasks").select("*, goals(title, color)")

    if dt:
        date_str = dt if isinstance(dt, str) else dt.isoformat()
        query = query.eq("scheduled_date", date_str).neq("status", "cancelled")
    else:
        query = query.eq("status", "todo")

    res = query.order("priority").execute()

    # Flatten joined goal data
    tasks = []
    for t in res.data:
        goal = t.pop("goals", None) or {}
        t["goal_title"] = goal.get("title")
        t["goal_color"] = goal.get("color")
        tasks.append(t)
    return tasks

def get_task(task_id):
    res = get_sb().table("tasks").select("*, goals(title, color)").eq("id", task_id).limit(1).execute()
    if not res.data:
        return None
    t = res.data[0]
    goal = t.pop("goals", None) or {}
    t["goal_title"] = goal.get("title")
    t["goal_color"] = goal.get("color")
    return t

def complete_task(task_id):
    get_sb().table("tasks").update({
        "status": "done",
        "completed_at": datetime.now().isoformat()
    }).eq("id", task_id).execute()

def get_tasks_by_goal(goal_id):
    res = get_sb().table("tasks").select("*").eq("goal_id", goal_id).order("status").order("priority").execute()
    return res.data

def delete_task(task_id):
    """Удалить задачу (или пометить cancelled)"""
    get_sb().table("tasks").update({"status": "cancelled"}).eq("id", task_id).execute()

def schedule_task(task_id, dt):
    date_str = dt if isinstance(dt, str) else dt.isoformat()
    get_sb().table("tasks").update({"scheduled_date": date_str}).eq("id", task_id).execute()


# ===== TIME LOGS =====

def start_timer(task_id):
    sb = get_sb()
    stop_active_timer()
    sb.table("tasks").update({"status": "in_progress"}).eq("id", task_id).execute()
    res = sb.table("time_logs").insert({
        "task_id": task_id,
        "started_at": datetime.now().isoformat()
    }).execute()
    return res.data[0]["id"]

def stop_active_timer():
    sb = get_sb()
    res = sb.table("time_logs").select("*").is_("ended_at", "null").order("id", desc=True).limit(1).execute()
    if not res.data:
        return 0
    active = res.data[0]
    now = datetime.now()
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
        "*, tasks(id, title, goal_id, goals(title))"
    ).is_("ended_at", "null").order("id", desc=True).limit(1).execute()

    if not res.data:
        return None
    row = res.data[0]
    task = row.pop("tasks", None) or {}
    goal = task.pop("goals", None) or {}
    return {
        **row,
        "task_id": task.get("id"),
        "task_title": task.get("title"),
        "goal_id": task.get("goal_id"),
        "goal_title": goal.get("title"),
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
            elapsed = (datetime.now() - datetime.fromisoformat(row["started_at"])).total_seconds() / 60
            total += elapsed
    return round(total, 1)

def get_daily_stats(days=30):
    sb = get_sb()
    since = (date.today() - timedelta(days=days)).isoformat() + "T00:00:00"
    res = sb.table("time_logs").select("started_at, duration_min").gte(
        "started_at", since
    ).not_.is_("ended_at", "null").execute()

    # Group by day
    by_day = {}
    for row in res.data:
        day = row["started_at"][:10]
        by_day.setdefault(day, {"total_min": 0, "tasks_worked": set()})
        by_day[day]["total_min"] += row["duration_min"] or 0

    return [
        {"day": day, "total_min": round(v["total_min"], 1)}
        for day, v in sorted(by_day.items())
    ]

def get_time_by_goal(days=30):
    sb = get_sb()
    since = (date.today() - timedelta(days=days)).isoformat() + "T00:00:00"
    res = sb.table("time_logs").select(
        "duration_min, tasks(goal_id, goals(id, title, color))"
    ).gte("started_at", since).not_.is_("ended_at", "null").execute()

    by_goal = {}
    for row in res.data:
        task = row.get("tasks") or {}
        goal = task.get("goals") or {}
        gid = goal.get("id")
        if not gid:
            continue
        if gid not in by_goal:
            by_goal[gid] = {"id": gid, "title": goal["title"], "color": goal["color"], "total_min": 0}
        by_goal[gid]["total_min"] += row["duration_min"] or 0

    return sorted(by_goal.values(), key=lambda x: x["total_min"], reverse=True)

def get_today_breakdown():
    """Детализация сегодняшних 4ч: по задачам с длительностями и целями"""
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
            duration = (datetime.now() - datetime.fromisoformat(row["started_at"])).total_seconds() / 60
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
    """Сегодняшнее время сгруппированное по целям"""
    entries = get_today_breakdown()
    by_goal = {}
    for e in entries:
        gid = e["goal_id"] or 0
        if gid not in by_goal:
            by_goal[gid] = {
                "goal_id": gid,
                "title": e["goal_title"],
                "color": e["goal_color"],
                "emoji": e["goal_emoji"],
                "total_min": 0,
                "tasks": {},
            }
        by_goal[gid]["total_min"] += e["duration_min"]
        tid = e["task_id"]
        if tid not in by_goal[gid]["tasks"]:
            by_goal[gid]["tasks"][tid] = {"title": e["task_title"], "min": 0}
        by_goal[gid]["tasks"][tid]["min"] += e["duration_min"]
    # Перевод в список
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

    # Hours spent
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
            # Сегодня ещё не набрал час — проверяем вчера
            check -= timedelta(days=1)
        else:
            break
    return streak
