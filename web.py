"""
ФОКУС-ТРЕКЕР v2 — Web Dashboard + REST API for Telegram WebApp
"""
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from datetime import date, datetime, timedelta
import json
import db
import httpx as _httpx
from config import WEB_PORT, WEB_HOST, DAILY_BUDGET_MINUTES, ICAL_URL, BOT_TOKEN, OWNER_ID

app = FastAPI(title="Фокус-Трекер")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ═══ HELPERS ═══

def build_work_goals():
    work_goals = db.get_goals(goal_type="work")
    result = []
    for g in work_goals:
        prog = db.get_goal_progress(g['id'])
        pct = int(prog['done_tasks'] / max(prog['total_tasks'], 1) * 100)
        result.append({**g, **prog, "pct": pct})
    return result

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


# ═══ PAGES ═══

@app.get("/", response_class=HTMLResponse)
async def webapp_page(request: Request):
    return templates.TemplateResponse(request, "webapp.html", {})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {
        "goals": build_work_goals(),
        "debts": build_debts(),
        "tasks_today": db.get_tasks_for_date(date.today().isoformat()),
        "worked_today": round(db.get_today_minutes(), 1),
        "budget": DAILY_BUDGET_MINUTES,
        "streak": db.get_streak(),
        "daily_stats": json.dumps(db.get_daily_stats(30)),
        "time_by_goal": json.dumps(db.get_time_by_goal(30)),
        "active_timer": db.get_active_timer(),
        "today": date.today().strftime("%d.%m.%Y"),
        "xp": db.get_xp(),
    })


# ═══ REST API — PLAN ═══

@app.get("/api/plan/today")
async def api_plan_today():
    today = date.today().isoformat()
    tasks = db.get_tasks_for_date(today)
    active = db.get_active_timer()
    breakdown = db.get_today_breakdown()
    by_goal = db.get_today_by_goal()
    schedule = db.get_today_schedule()

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
        "pomodoros": db.get_today_pomodoros(),
        "streak": db.get_streak(),
        "timeline": timeline,
        "by_goal": by_goal,
        "schedule": schedule,
        "xp": db.get_xp(),
    }

@app.post("/api/plan/suggest")
async def api_plan_suggest():
    """Авто-план: подбирает задачи по приоритету на 4ч"""
    today = date.today().isoformat()
    all_todo = db.get_tasks_for_date(None)

    # Приоритет: агентство (1) > ПМ+СММ (2) > сайты (3)
    def prio(t):
        gid = t.get("goal_id") or 999
        try:
            goals = db.get_goals(goal_type="work")
            goal_ids = [g["id"] for g in goals]
            return goal_ids.index(gid) if gid in goal_ids else 999
        except (ValueError, IndexError):
            return 999

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


# ═══ REST API — TIMER ═══

@app.post("/api/timer/start/{task_id}")
async def api_timer_start(task_id: int):
    log_id = db.start_timer(task_id)
    return {"ok": True, "log_id": log_id}

@app.post("/api/timer/stop")
async def api_timer_stop():
    duration = db.stop_active_timer()
    # Начисляем XP за помодорку если >= 25 мин
    xp_earned = 0
    if duration >= 25:
        pomodoros = int(duration // 30) or 1
        xp_earned = pomodoros * db.XP_POMODORO
        db.add_xp(xp_earned, "pomodoro")
    return {"ok": True, "duration_min": duration, "xp_earned": xp_earned}


# ═══ REST API — TASKS ═══

@app.post("/api/tasks/{task_id}/complete")
async def api_task_complete(task_id: int):
    db.stop_active_timer()
    db.complete_task(task_id)
    # XP за завершение задачи
    xp = db.add_xp(db.XP_TASK_DONE, "task_done")
    # Проверяем полный день
    bonus = 0
    today_min = db.get_today_minutes()
    if today_min >= DAILY_BUDGET_MINUTES:
        bonus += db.XP_FULL_DAY
    # Проверяем все задачи дня выполнены
    today_tasks = db.get_tasks_for_date(date.today().isoformat())
    if today_tasks and all(t["status"] == "done" for t in today_tasks):
        bonus += db.XP_ALL_TASKS
    if bonus:
        db.add_xp(bonus, "bonus")
    return {"ok": True, "xp_earned": db.XP_TASK_DONE + bonus, "xp": db.get_xp()}

@app.post("/api/tasks/add")
async def api_add_task(request: Request):
    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        return {"ok": False, "error": "Title required"}
    goal_id = body.get("goal_id")
    estimate_min = body.get("estimate_min", 60)
    scheduled_date = body.get("scheduled_date", date.today().isoformat())
    priority = body.get("priority", 1)
    task_id = db.add_task(
        goal_id=goal_id, title=title,
        estimate_min=estimate_min, scheduled_date=scheduled_date,
        priority=priority,
    )
    return {"ok": True, "task_id": task_id}

@app.post("/api/notify")
async def api_notify(request: Request):
    """Send notification to bot owner via Telegram"""
    body = await request.json()
    text = body.get("text", "")
    if not text or not BOT_TOKEN or not OWNER_ID:
        return {"ok": False}
    try:
        async with _httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": OWNER_ID, "text": text, "parse_mode": "HTML"},
                timeout=5,
            )
        return {"ok": True}
    except Exception:
        return {"ok": False}

@app.put("/api/tasks/{task_id}")
async def api_update_task(task_id: int, request: Request):
    body = await request.json()
    allowed = {"title", "estimate_min", "goal_id", "scheduled_date", "priority"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if updates:
        db.update_task(task_id, **updates)
    return {"ok": True}

@app.delete("/api/tasks/{task_id}")
async def api_delete_task(task_id: int):
    db.delete_task(task_id)
    return {"ok": True}


# ═══ REST API — GOALS ═══

@app.get("/api/goals")
async def api_goals():
    return {"work": build_work_goals(), "debts": build_debts()}

@app.post("/api/goals")
async def api_create_goal(request: Request):
    body = await request.json()
    allowed = {"title", "description", "type", "zone", "target_rub", "emoji", "color", "priority"}
    data = {k: v for k, v in body.items() if k in allowed}
    goal_id = db.create_goal(**data)
    return {"ok": True, "goal_id": goal_id}

@app.put("/api/goals/{goal_id}")
async def api_update_goal(goal_id: int, request: Request):
    body = await request.json()
    allowed = {"title", "description", "target_rub", "emoji", "color", "priority", "status"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if updates:
        db.update_goal(goal_id, **updates)
    return {"ok": True}

@app.delete("/api/goals/{goal_id}")
async def api_delete_goal(goal_id: int):
    db.delete_goal(goal_id)
    return {"ok": True}


# ═══ REST API — DEBTS & PAYMENTS ═══

@app.get("/api/debts")
async def api_debts():
    return build_debts()

@app.post("/api/debts/pay")
async def api_pay_debt(request: Request):
    body = await request.json()
    goal_id = body.get("goal_id")
    amount = body.get("amount", 0)
    note = body.get("note", "")
    if not goal_id or amount <= 0:
        return {"ok": False, "error": "goal_id and amount > 0 required"}
    new_paid = db.add_payment(goal_id, amount, note)
    return {"ok": True, "new_paid": new_paid, "debts": build_debts()}


# ═══ REST API — SALES ═══

@app.get("/api/sales")
async def api_sales():
    return db.get_sales_summary(30)

@app.post("/api/sales")
async def api_add_sale(request: Request):
    body = await request.json()
    product_type = body.get("product_type", "smm")
    revenue = body.get("revenue", 0)
    cost = body.get("cost", 0)
    client_name = body.get("client_name", "")
    note = body.get("note", "")
    sale = db.add_sale(product_type, revenue, cost, client_name, note)
    # Автоматически направляем маржу на текущий приоритетный долг
    margin = revenue - cost
    auto_paid = None
    if margin > 0:
        debts = db.get_debts()
        for d in debts:
            remaining = (d.get("target_rub") or 0) - (d.get("paid_rub") or 0)
            if remaining > 0:
                pay_amount = min(margin, remaining)
                db.add_payment(d["id"], pay_amount, f"Авто из продажи: {client_name}")
                auto_paid = {"goal_id": d["id"], "title": d["title"], "amount": pay_amount}
                margin -= pay_amount
                if margin <= 0:
                    break
    return {"ok": True, "sale": sale, "auto_paid": auto_paid, "debts": build_debts()}


# ═══ REST API — XP ═══

@app.get("/api/xp")
async def api_xp():
    xp = db.get_xp()
    streak = db.get_streak()
    return {**xp, "streak": streak, "streak_bonus": streak * db.XP_STREAK_MULTIPLIER}


# ═══ REST API — REWARDS ═══

@app.get("/api/rewards")
async def api_rewards():
    xp = db.get_xp()
    rewards = db.get_rewards()
    history = db.get_reward_history(10)
    return {"rewards": rewards, "xp": xp, "history": history}

@app.post("/api/rewards/claim/{reward_id}")
async def api_claim_reward(reward_id: int):
    success, message = db.claim_reward(reward_id)
    return {"ok": success, "message": message, "xp": db.get_xp()}

@app.post("/api/rewards")
async def api_create_reward(request: Request):
    body = await request.json()
    rid = db.create_reward(
        title=body.get("title", ""),
        emoji=body.get("emoji", "🎁"),
        cost_xp=body.get("cost_xp", 100),
        category=body.get("category", "food"),
    )
    return {"ok": True, "reward_id": rid}

@app.put("/api/rewards/{reward_id}")
async def api_update_reward(reward_id: int, request: Request):
    body = await request.json()
    allowed = {"title", "emoji", "cost_xp", "category"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if updates:
        db.update_reward(reward_id, **updates)
    return {"ok": True}

@app.delete("/api/rewards/{reward_id}")
async def api_delete_reward(reward_id: int):
    db.delete_reward(reward_id)
    return {"ok": True}


# ═══ REST API — SCHEDULE ═══

@app.get("/api/schedule")
async def api_schedule():
    return {"schedule": db.get_schedule(), "today": db.get_today_schedule()}

@app.put("/api/schedule/{weekday}")
async def api_update_schedule(weekday: int, request: Request):
    body = await request.json()
    db.update_schedule(weekday, body.get("focus", ""), body.get("hours", 4))
    return {"ok": True}


# ═══ REST API — STATS ═══

@app.get("/api/stats")
async def api_stats():
    return {
        "today_minutes": db.get_today_minutes(),
        "pomodoros": db.get_today_pomodoros(),
        "streak": db.get_streak(),
        "daily": db.get_daily_stats(30),
        "by_goal": db.get_time_by_goal(30),
        "active": db.get_active_timer(),
        "xp": db.get_xp(),
        "sales": db.get_sales_summary(30),
        "debts": build_debts(),
    }

@app.get("/api/life-goals")
async def api_life_goals():
    return {"debts": build_debts()}


# ═══ REST API — MILESTONES ═══

@app.get("/api/milestones")
async def api_milestones():
    return {"milestones": db.get_milestones()}

@app.post("/api/milestones")
async def api_create_milestone(request: Request):
    body = await request.json()
    mid = db.create_milestone(
        phase=body.get("phase", ""),
        title=body.get("title", ""),
        start_date=body.get("start_date"),
        end_date=body.get("end_date"),
        color=body.get("color", "#8B0020"),
    )
    return {"ok": True, "id": mid}

@app.put("/api/milestones/{mid}")
async def api_update_milestone(mid: int, request: Request):
    body = await request.json()
    allowed = {"phase", "title", "start_date", "end_date", "color", "status"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if updates:
        db.update_milestone(mid, **updates)
    return {"ok": True}

@app.delete("/api/milestones/{mid}")
async def api_delete_milestone(mid: int):
    db.delete_milestone(mid)
    return {"ok": True}


# ═══ REST API — CALENDAR ═══

@app.get("/api/calendar/day")
async def api_calendar_day(date_str: str = ""):
    d = date_str or date.today().isoformat()
    tasks = db.get_tasks_for_range(d, d)
    logs = db.get_timelogs_for_range(d, d)
    ical = await _get_ical_events(d, d)
    return {"date": d, "tasks": tasks, "logs": logs, "ical_events": ical}

@app.get("/api/calendar/week")
async def api_calendar_week(date_str: str = ""):
    d = date.fromisoformat(date_str) if date_str else date.today()
    start = d - timedelta(days=d.weekday())  # Monday
    end = start + timedelta(days=6)
    tasks = db.get_tasks_for_range(start.isoformat(), end.isoformat())
    logs = db.get_timelogs_for_range(start.isoformat(), end.isoformat())
    ical = await _get_ical_events(start.isoformat(), end.isoformat())
    return {
        "start": start.isoformat(), "end": end.isoformat(),
        "tasks": tasks, "logs": logs, "ical_events": ical,
    }

@app.get("/api/calendar/month")
async def api_calendar_month(month: str = ""):
    if month:
        y, m = month.split("-")
        start = date(int(y), int(m), 1)
    else:
        start = date.today().replace(day=1)
    if start.month == 12:
        end = date(start.year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(start.year, start.month + 1, 1) - timedelta(days=1)
    tasks = db.get_tasks_for_range(start.isoformat(), end.isoformat())
    milestones = db.get_milestones()
    ical = await _get_ical_events(start.isoformat(), end.isoformat())
    return {
        "start": start.isoformat(), "end": end.isoformat(),
        "tasks": tasks, "milestones": milestones, "ical_events": ical,
    }


# ═══ ICAL CACHE ═══

_ical_cache = {"data": [], "fetched_at": None}

async def _get_ical_events(start_str, end_str):
    """Parse iCal URL, cache 15 min"""
    if not ICAL_URL:
        return []
    import time
    now = time.time()
    if _ical_cache["fetched_at"] and (now - _ical_cache["fetched_at"]) < 900:
        events = _ical_cache["data"]
    else:
        try:
            import httpx
            from icalendar import Calendar
            async with httpx.AsyncClient() as client:
                resp = await client.get(ICAL_URL, timeout=10)
                cal = Calendar.from_ical(resp.text)
                events = []
                for comp in cal.walk():
                    if comp.name == "VEVENT":
                        dtstart = comp.get("dtstart")
                        dtend = comp.get("dtend")
                        events.append({
                            "title": str(comp.get("summary", "")),
                            "start": dtstart.dt.isoformat() if dtstart else None,
                            "end": dtend.dt.isoformat() if dtend else None,
                            "all_day": not hasattr(dtstart.dt, "hour") if dtstart else True,
                        })
                _ical_cache["data"] = events
                _ical_cache["fetched_at"] = now
        except Exception as e:
            print(f"iCal fetch error: {e}")
            return []

    # Filter to date range
    filtered = []
    for ev in events:
        if ev["start"] and ev["start"][:10] >= start_str and ev["start"][:10] <= end_str:
            filtered.append(ev)
    return filtered


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT)
