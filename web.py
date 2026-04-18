"""
Trigger Tracker — Web Dashboard + REST API for Telegram WebApp
"""
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from datetime import date, datetime
import json
import db
from config import WEB_PORT, WEB_HOST, DAILY_BUDGET_MINUTES

app = FastAPI(title="Trigger Tracker")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

ZONES_META = {
    "debts":  {"title": "🔥 Долги",      "color": "#CD5C5C"},
    "goals":  {"title": "🎯 Цели",       "color": "#6083C8"},
    "travel": {"title": "✈️ Путешествия", "color": "#D4A574"},
    "future": {"title": "💰 Будущее",    "color": "#6EBF8B"},
    "wife":   {"title": "💕 Жене",       "color": "#C97FB5"},
}

def build_zones():
    life_goals = db.get_life_goals()
    zones = []
    for zone_key, meta in ZONES_META.items():
        items = life_goals.get(zone_key, [])
        if not items:
            continue
        total_target = sum(g.get("target_rub") or 0 for g in items)
        total_paid = sum(g.get("paid_rub") or 0 for g in items)
        total_monthly = sum(g.get("monthly_rub") or 0 for g in items)
        total_remaining = max(total_target - total_paid, 0)
        pct = int(total_paid / total_target * 100) if total_target > 0 else 0
        for g in items:
            if g.get("target_rub"):
                g["pct"] = int((g.get("paid_rub") or 0) / g["target_rub"] * 100)
                g["remaining_rub"] = max(g["target_rub"] - (g.get("paid_rub") or 0), 0)
            else:
                g["pct"] = 0
                g["remaining_rub"] = 0
        zones.append({
            "key": zone_key, "title": meta["title"], "color": meta["color"],
            "goals_list": items, "total_target": total_target,
            "total_paid": total_paid, "total_monthly": total_monthly,
            "total_remaining": total_remaining, "pct": pct, "count": len(items),
        })
    return zones

def build_work_goals():
    work_goals = db.get_goals(goal_type="work")
    result = []
    for g in work_goals:
        prog = db.get_goal_progress(g['id'])
        pct = int(prog['done_tasks'] / max(prog['total_tasks'], 1) * 100)
        result.append({**g, **prog, "pct": pct})
    return result


# ═══ PAGES ═══

@app.get("/", response_class=HTMLResponse)
async def webapp_page(request: Request):
    return templates.TemplateResponse(request, "webapp.html", {})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {
        "goals": build_work_goals(),
        "zones": build_zones(),
        "tasks_today": db.get_tasks_for_date(date.today().isoformat()),
        "worked_today": round(db.get_today_minutes(), 1),
        "budget": DAILY_BUDGET_MINUTES,
        "streak": db.get_streak(),
        "daily_stats": json.dumps(db.get_daily_stats(30)),
        "time_by_goal": json.dumps(db.get_time_by_goal(30)),
        "active_timer": db.get_active_timer(),
        "today": date.today().strftime("%d.%m.%Y"),
    })


# ═══ REST API FOR WEBAPP ═══

@app.get("/api/plan/today")
async def api_plan_today():
    today = date.today().isoformat()
    tasks = db.get_tasks_for_date(today)
    active = db.get_active_timer()
    breakdown = db.get_today_breakdown()
    by_goal = db.get_today_by_goal()

    timeline = []
    for e in breakdown:
        start_dt = datetime.fromisoformat(e["started_at"])
        end_dt = datetime.fromisoformat(e["ended_at"]) if e["ended_at"] else None
        timeline.append({
            "start_time": start_dt.strftime("%H:%M"),
            "end_time": end_dt.strftime("%H:%M") if end_dt else "сейчас",
            "task_title": e["task_title"],
            "goal_emoji": e.get("goal_emoji", "🎯"),
            "duration_min": e["duration_min"],
            "active": e["active"],
        })

    return {
        "tasks": tasks,
        "goals": build_work_goals(),
        "active": active,
        "today_min": round(db.get_today_minutes(), 1),
        "streak": db.get_streak(),
        "timeline": timeline,
        "by_goal": by_goal,
    }

@app.get("/api/goals")
async def api_goals():
    return {"work": build_work_goals(), "zones": build_zones()}

@app.get("/api/stats")
async def api_stats():
    return {
        "today_minutes": db.get_today_minutes(),
        "streak": db.get_streak(),
        "daily": db.get_daily_stats(30),
        "by_goal": db.get_time_by_goal(30),
        "active": db.get_active_timer(),
    }

@app.get("/api/life-goals")
async def api_life_goals():
    return {"zones": build_zones()}

@app.post("/api/timer/start/{task_id}")
async def api_timer_start(task_id: int):
    log_id = db.start_timer(task_id)
    return {"ok": True, "log_id": log_id}

@app.post("/api/timer/stop")
async def api_timer_stop():
    duration = db.stop_active_timer()
    return {"ok": True, "duration_min": duration}

@app.post("/api/tasks/{task_id}/complete")
async def api_task_complete(task_id: int):
    db.stop_active_timer()
    db.complete_task(task_id)
    return {"ok": True}

@app.post("/api/tasks/add")
async def api_add_task(request: Request):
    """Add a custom task from the web UI"""
    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        return {"ok": False, "error": "Title required"}
    goal_id = body.get("goal_id")
    estimate_min = body.get("estimate_min", 60)
    scheduled_date = body.get("scheduled_date", date.today().isoformat())
    task_id = db.add_task(
        goal_id=goal_id,
        title=title,
        estimate_min=estimate_min,
        scheduled_date=scheduled_date,
    )
    return {"ok": True, "task_id": task_id}

@app.delete("/api/tasks/{task_id}")
async def api_delete_task(task_id: int):
    """Delete (cancel) a task"""
    db.delete_task(task_id)
    return {"ok": True}

@app.post("/api/plan/suggest")
async def api_plan_suggest():
    """Авто-план: подбирает задачи по приоритету стратегии на 4ч"""
    today = date.today().isoformat()
    all_todo = db.get_tasks_for_date(None)
    priority_order = [3, 2, 1, 4, 5, 6]

    def prio(t):
        gid = t.get("goal_id") or 999
        try: return priority_order.index(gid)
        except ValueError: return 999

    candidates = sorted(all_todo, key=lambda t: (prio(t), t["estimate_min"]))
    total = 0
    scheduled = []
    for t in candidates:
        if total + t["estimate_min"] <= DAILY_BUDGET_MINUTES + 15:
            db.schedule_task(t["id"], today)
            scheduled.append(t)
            total += t["estimate_min"]
            if total >= DAILY_BUDGET_MINUTES - 15:
                break
    return {"ok": True, "scheduled": len(scheduled), "total_min": total}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT)
